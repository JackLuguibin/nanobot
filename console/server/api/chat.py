"""API routes for chat and streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from loguru import logger

from console.server.api.models import ChatRequest, ChatResponse
from console.server.api.state import get_state
from console.server.api.websocket import get_connection_manager, handle_websocket

router = APIRouter(prefix="/api")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


def _agent_unavailable_detail(state) -> str:
    """返回无法使用 Agent 时的具体原因，便于前端展示。"""
    if state.bot_id == "_empty":
        return "No bot available. Please create or select a bot first."
    return (
        "Agent not running. Please configure an API key in Console Settings or in the config file "
        "(e.g. providers.openai.apiKey), or set the key in .env next to your config."
    )


# ---------------------------------------------------------------------------
# Chat (non-streaming)
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(request: ChatRequest) -> ChatResponse:
    """Send a chat message and get a response."""
    state = _resolve_state(request.bot_id)
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(status_code=503, detail=_agent_unavailable_detail(state))

    session_key = request.session_key
    if session_key is None:
        session = await state.create_session()
        session_key = session["key"]

    try:
        from console.server.extension.message_source import SOURCE_MAIN_AGENT, set_message_source_context

        async def silent_progress(content: str) -> None:
            pass

        set_message_source_context(SOURCE_MAIN_AGENT)
        response = await agent_loop.process_direct(
            content=request.message,
            session_key=session_key,
            channel="console",
            chat_id="web",
            on_progress=silent_progress,
        )

        state.increment_messages()

        message = response.content if response else ""

        return ChatResponse(
            session_key=session_key,
            message=message,
            done=True,
        )

    except Exception as e:
        logger.error("Error processing chat message: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat (streaming)
# ---------------------------------------------------------------------------


@router.post("/chat/stream")
async def send_chat_message_stream(request: ChatRequest):
    """Send a chat message with streaming response (SSE)."""
    from console.server.extension.message_source import (
        SOURCE_MAIN_AGENT,
        SOURCE_SUB_AGENT,
        set_message_source_context,
    )
    from console.server.extension.subagent_events import set_subagent_callback

    state = _resolve_state(request.bot_id)
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(status_code=503, detail=_agent_unavailable_detail(state))

    session_key = request.session_key
    if session_key is None:
        session = await state.create_session()
        session_key = session["key"]

    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'session_key', 'session_key': session_key})}\n\n"

            queue: asyncio.Queue[str | None] = asyncio.Queue()
            response_holder: list[str] = []
            agent_failed: list[bool] = [False]
            subagent_active: set[str] = set()
            stream_closed = False
            agent_finished = False

            async def maybe_finish_stream() -> None:
                nonlocal stream_closed
                if stream_closed:
                    return
                if agent_finished and not subagent_active:
                    stream_closed = True
                    await queue.put(None)

            async def stream_progress(content: str, *, tool_hint: bool = False) -> None:
                await queue.put(
                    f"data: {json.dumps({'type': 'chat_token', 'content': content})}\n\n"
                )

            async def on_subagent_event(event: dict[str, Any]) -> None:
                """Handle subagent events and forward to SSE."""
                await queue.put(f"data: {json.dumps(event)}\n\n")

                subagent_id = event.get("subagent_id")
                event_type = event.get("type")
                if event_type == "subagent_start" and isinstance(subagent_id, str):
                    subagent_active.add(subagent_id)
                elif event_type == "subagent_done" and isinstance(subagent_id, str):
                    subagent_active.discard(subagent_id)

                if event_type != "subagent_done":
                    await maybe_finish_stream()
                    return

                label = event.get("label", "task")
                task = event.get("task", "")
                result = event.get("result", "")
                status = event.get("status", "error")
                status_text = "completed successfully" if status == "ok" else "failed"

                summarize_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

                try:
                    set_message_source_context(SOURCE_SUB_AGENT)
                    follow_up_response = await agent_loop.process_direct(
                        content=summarize_content,
                        session_key=session_key,
                        channel="console",
                        chat_id="web",
                        on_progress=stream_progress,
                    )

                    if follow_up_response:
                        content = follow_up_response.content if hasattr(follow_up_response, 'content') else follow_up_response
                        await queue.put(
                            f"data: {json.dumps({'type': 'assistant_message', 'content': content, 'source': 'sub_agent'})}\n\n"
                        )
                except Exception as e:
                    logger.warning("Failed to process subagent result: {}", e)
                finally:
                    await maybe_finish_stream()

            set_subagent_callback(agent_loop, on_subagent_event)

            async def run_agent() -> None:
                nonlocal agent_finished
                try:
                    set_message_source_context(SOURCE_MAIN_AGENT)
                    response_text = await agent_loop.process_direct(
                        content=request.message,
                        session_key=session_key,
                        channel="console",
                        chat_id="web",
                        on_progress=stream_progress,
                    )
                    response_holder.append(response_text.content if response_text else "")
                except Exception as e:
                    agent_failed[0] = True
                    await queue.put(f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n")
                finally:
                    nonlocal agent_finished
                    agent_finished = True
                    await maybe_finish_stream()

            task = asyncio.create_task(run_agent())
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk

            await task

            if agent_failed[0]:
                return

            state.increment_messages()

            try:
                manager = get_connection_manager()
                status = await state.get_status()
                sessions = await state.get_sessions()
                await manager.broadcast_status_update(status, state.bot_id)
                await manager.broadcast_sessions_update(sessions, state.bot_id)
            except Exception as e:
                logger.warning("Failed to broadcast status update: {}", e)

            response_text = response_holder[0] if response_holder else ""
            yield f"data: {json.dumps({'type': 'chat_done', 'done': True, 'content': response_text, 'source': 'main_agent'})}\n\n"

        except Exception as e:
            logger.error("Error in streaming chat: {}", e)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time updates."""
    await handle_websocket(websocket)

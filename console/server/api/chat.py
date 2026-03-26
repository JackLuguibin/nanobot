"""API routes for chat."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from console.server.api.state import get_state
from console.server.models.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat")


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


@router.post("", response_model=ChatResponse)
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
        from console.server.extension.message_source import (
            SOURCE_MAIN_AGENT,
            set_message_source_context,
        )

        async def silent_progress(content: str, *, tool_hint: bool = False) -> None:
            """与流式接口一致，process_direct 在工具调用时会传入 tool_hint=True。"""
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

"""API routes for the console server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from console.server.api.models import (
    ChannelStatus,
    ChatRequest,
    ChatResponse,
    ConfigUpdateRequest,
    CronAddRequest,
    CronJobResponse,
    MCPStatus,
    SessionInfo,
    StatusResponse,
    ToolCallLog,
)
from console.server.api.state import get_state, get_state_manager
from console.server.api.websocket import get_connection_manager, handle_websocket

router = APIRouter(prefix="/api")


def _resolve_state(bot_id: str | None = None):
    """Resolve BotState for a given bot_id (or default)."""
    return get_state(bot_id)


# ====================
# Bot Management Endpoints
# ====================


class BotCreateRequest(BaseModel):
    name: str
    source_config: dict[str, Any] | None = None


class BotInfoResponse(BaseModel):
    id: str
    name: str
    config_path: str
    workspace_path: str
    created_at: str
    updated_at: str
    is_default: bool = False
    running: bool = False


class SetDefaultRequest(BaseModel):
    bot_id: str


@router.get("/bots")
async def list_bots() -> list[BotInfoResponse]:
    """List all registered bots."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()
    default_id = registry.default_bot_id
    result = []

    for bot in registry.list_bots():
        running = False
        if manager.has_state(bot.id):
            running = manager.get_state(bot.id).is_running
        result.append(
            BotInfoResponse(
                id=bot.id,
                name=bot.name,
                config_path=bot.config_path,
                workspace_path=bot.workspace_path,
                created_at=bot.created_at,
                updated_at=bot.updated_at,
                is_default=(bot.id == default_id),
                running=running,
            )
        )

    return result


@router.get("/bots/{bot_id}")
async def get_bot(bot_id: str) -> BotInfoResponse:
    """Get a specific bot."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    running = False
    if manager.has_state(bot.id):
        running = manager.get_state(bot.id).is_running

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=running,
    )


@router.post("/bots")
async def create_bot(request: BotCreateRequest) -> BotInfoResponse:
    """Create a new bot with independent config and workspace."""
    from console.server.bot_registry import get_registry
    from console.server.main import _initialize_bot
    from nanobot.config.loader import load_config

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.create_bot(request.name, request.source_config)

    try:
        config = load_config(Path(bot.config_path))
        state = _initialize_bot(bot.id, config, Path(bot.config_path))
        manager.set_state(bot.id, state)
        if state.cron_service and state.agent_loop:
            await state.cron_service.start()
    except Exception as e:
        logger.warning("Created bot '{}' but failed to initialize: {}", bot.id, e)

    running = manager.has_state(bot.id) and manager.get_state(bot.id).is_running

    await get_connection_manager().broadcast_bots_update()

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=running,
    )


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str) -> dict[str, str]:
    """Delete a bot and its workspace."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    remaining = registry.list_bots()
    if len(remaining) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last bot")

    old_state = manager.remove_state(bot_id)
    if old_state:
        if old_state.cron_service:
            old_state.cron_service.stop()
        if old_state.agent_loop:
            try:
                await old_state.stop_current_task()
            except Exception:
                pass

    registry.delete_bot(bot_id)

    await get_connection_manager().broadcast_bots_update()

    return {"status": "deleted", "bot_id": bot_id}


@router.put("/bots/default")
async def set_default_bot(request: SetDefaultRequest) -> dict[str, str]:
    """Set the default bot."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    if not registry.set_default(request.bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")

    get_state_manager().default_bot_id = request.bot_id

    await get_connection_manager().broadcast_bots_update()

    return {"status": "ok", "default_bot_id": request.bot_id}


@router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str) -> BotInfoResponse:
    """Start (enable) a bot: load config, initialize state, and run."""
    from pathlib import Path

    from console.server.bot_registry import get_registry
    from console.server.extension.config_loader import load_bot_config
    from console.server.main import _initialize_bot

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    if manager.has_state(bot_id) and manager.get_state(bot_id).is_running:
        state = manager.get_state(bot_id)
        return BotInfoResponse(
            id=bot.id,
            name=bot.name,
            config_path=bot.config_path,
            workspace_path=bot.workspace_path,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            is_default=(bot.id == registry.default_bot_id),
            running=True,
        )

    config_path = Path(bot.config_path)
    if not config_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Config file not found: {config_path}",
        )

    try:
        config = load_bot_config(config_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Config load failed: {e}") from e

    try:
        state = _initialize_bot(bot_id, config, config_path)
        if state.workspace:
            try:
                from console.server.extension.agents import AgentManager

                agent_manager = AgentManager(bot_id, state.workspace)
                await agent_manager.initialize()
                state._agent_manager = agent_manager
                logger.info("AgentManager initialized for bot '{}'", bot_id)
            except Exception as e:
                logger.warning("Failed to initialize AgentManager for bot '{}': {}", bot_id, e)
        manager.set_state(bot_id, state)
        if state.cron_service and state.agent_loop:
            await state.cron_service.start()
        logger.info("Started bot '{}' ({})", bot.name, bot_id)
    except Exception as e:
        logger.exception("Failed to start bot '{}'", bot_id)
        raise HTTPException(status_code=500, detail=str(e)) from e

    await get_connection_manager().broadcast_bots_update()

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=manager.get_state(bot_id).is_running,
    )


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str) -> BotInfoResponse:
    """Stop (disable) a bot: shutdown and remove its state. Bot remains in registry."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not manager.has_state(bot_id):
        return BotInfoResponse(
            id=bot.id,
            name=bot.name,
            config_path=bot.config_path,
            workspace_path=bot.workspace_path,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            is_default=(bot.id == registry.default_bot_id),
            running=False,
        )

    old_state = manager.remove_state(bot_id)
    if old_state:
        if old_state.cron_service:
            old_state.cron_service.stop()
        if old_state.agent_loop:
            try:
                await old_state.stop_current_task()
            except Exception:
                pass
    logger.info("Stopped bot '{}' ({})", bot.name, bot_id)

    await get_connection_manager().broadcast_bots_update()

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=False,
    )


# ====================
# Status Endpoints
# ====================


@router.get("/status", response_model=StatusResponse)
async def get_status(bot_id: str | None = Query(None)) -> StatusResponse:
    """Get the overall bot status."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return StatusResponse(**status)


@router.get("/usage/history")
async def get_usage_history(
    bot_id: str | None = Query(None),
    days: int = Query(14, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Get daily token usage history for the chart (includes cost_usd, cost_by_model)."""
    from console.server.extension.usage import get_usage_history

    state = _resolve_state(bot_id)
    return get_usage_history(state.bot_id, days=days)


@router.get("/usage/cost")
async def get_usage_cost(
    bot_id: str | None = Query(None),
    date_str: str | None = Query(None, description="ISO date, e.g. 2025-03-10"),
) -> dict[str, Any]:
    """Get cost for a specific date (default: today)."""
    from datetime import date

    from console.server.extension.usage import get_usage_cost as _get_usage_cost

    state = _resolve_state(bot_id)
    target = date.fromisoformat(date_str) if date_str else None
    return _get_usage_cost(state.bot_id, target)


@router.get("/channels", response_model=list[ChannelStatus])
async def get_channels(bot_id: str | None = Query(None)) -> list[ChannelStatus]:
    """Get all channels from config, merged with runtime status when available."""
    state = _resolve_state(bot_id)
    channels = await state.get_channels()
    return [ChannelStatus(**ch) for ch in channels]


class ChannelUpdateRequest(BaseModel):
    """Request body for updating a channel."""

    data: dict[str, Any]


@router.put("/channels/{name}")
async def update_channel(
    name: str,
    request: ChannelUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Update a channel's configuration."""
    state = _resolve_state(bot_id)
    try:
        return await state.update_channel(name, request.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/channels/{name}")
async def delete_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Disable a channel (set enabled=False)."""
    state = _resolve_state(bot_id)
    ok = await state.delete_channel(name)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {name}")
    return {"status": "ok"}


@router.get("/mcp", response_model=list[MCPStatus])
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


def _activity_to_tool_log(entry: dict) -> dict:
    """Convert activity entry to ToolCallLog format."""
    from datetime import datetime

    data = entry.get("data") or {}
    ts = entry.get("timestamp", 0)
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts)
        ts_str = dt.isoformat()
    else:
        ts_str = str(ts)
    return {
        "id": entry.get("id", ""),
        "tool_name": data.get("tool_name", ""),
        "arguments": data.get("arguments") or {},
        "result": data.get("result") or data.get("error"),
        "status": "success" if data.get("status") == "success" else "error",
        "duration_ms": data.get("duration_ms", 0),
        "timestamp": ts_str,
    }


@router.get("/tools/log", response_model=list[ToolCallLog])
async def get_tool_logs(
    limit: int = 50,
    tool_name: str | None = None,
    bot_id: str | None = Query(None),
) -> list[ToolCallLog]:
    """Get tool call logs (in-memory + persisted activity)."""
    state = _resolve_state(bot_id)
    logs = list(state.tool_call_logs)

    # Merge with persisted activity (for tool_call type)
    if state.bot_id != "_empty":
        try:
            from console.server.extension.activity import get_activity

            activity = get_activity(state.bot_id, limit=limit * 2, activity_type="tool_call")
            seen_ids = {log.get("id") for log in logs}
            for entry in activity:
                if entry.get("id") in seen_ids:
                    continue
                log = _activity_to_tool_log(entry)
                if tool_name and log.get("tool_name") != tool_name:
                    continue
                logs.append(log)
                seen_ids.add(entry.get("id"))
        except Exception:
            pass

    if tool_name:
        logs = [log for log in logs if log.get("tool_name") == tool_name]

    logs = sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]

    return [ToolCallLog(**log) for log in logs]


# ====================
# Session Endpoints
# ====================


@router.get("/sessions")
async def list_sessions(bot_id: str | None = Query(None)) -> list[SessionInfo]:
    """List all sessions."""
    state = _resolve_state(bot_id)
    sessions = await state.get_sessions()
    return [SessionInfo(**s) for s in sessions]


@router.get("/sessions/{key}")
async def get_session(key: str, bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get a specific session with full history."""
    state = _resolve_state(bot_id)
    session = await state.get_session(key)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions")
async def create_session(key: str | None = None, bot_id: str | None = Query(None)) -> SessionInfo:
    """Create a new session."""
    state = _resolve_state(bot_id)
    session = await state.create_session(key)

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        sessions = await state.get_sessions()
        await manager.broadcast_status_update(status, state.bot_id)
        await manager.broadcast_sessions_update(sessions, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return SessionInfo(**session)


@router.delete("/sessions/{key}")
async def delete_session(key: str, bot_id: str | None = Query(None)) -> dict[str, str]:
    """Delete a session."""
    state = _resolve_state(bot_id)
    deleted = await state.delete_session(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        sessions = await state.get_sessions()
        await manager.broadcast_status_update(status, state.bot_id)
        await manager.broadcast_sessions_update(sessions, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "deleted", "key": key}


# ====================
# Chat Endpoints
# ====================


def _agent_unavailable_detail(state) -> str:
    """返回无法使用 Agent 时的具体原因，便于前端展示。"""
    if state.bot_id == "_empty":
        return "No bot available. Please create or select a bot first."
    return (
        "Agent not running. Please configure an API key in Console Settings or in the config file "
        "(e.g. providers.openai.apiKey), or set the key in .env next to your config."
    )


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

        return ChatResponse(
            session_key=session_key,
            message=response or "",
            done=True,
        )

    except Exception as e:
        logger.error("Error processing chat message: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


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
                        await queue.put(
                            f"data: {json.dumps({'type': 'assistant_message', 'content': follow_up_response, 'source': 'sub_agent'})}\n\n"
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
                    response_holder.append(response_text or "")
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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time updates."""
    await handle_websocket(websocket)


# ====================
# Memory Endpoints
# ====================


@router.get("/memory")
async def get_memory(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Get long-term memory (MEMORY.md) and history (HISTORY.md)."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    from nanobot.agent.memory import MemoryStore

    store = MemoryStore(workspace)
    return {
        "long_term": store.read_long_term(),
        "history": store.history_file.read_text(encoding="utf-8")
        if store.history_file.exists()
        else "",
    }


def _read_workspace_file(workspace: Path, filename: str) -> str:
    """Read a file from workspace, return empty string if not found."""
    path = workspace / filename
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _resolve_workspace_path(workspace: Path, rel_path: str) -> Path | None:
    """Resolve relative path within workspace. Returns None if path escapes workspace."""
    if not workspace or not workspace.exists():
        return None
    try:
        resolved = (workspace / rel_path).resolve()
        if not str(resolved).startswith(str(workspace.resolve())):
            return None
        return resolved
    except Exception:
        return None


@router.get("/workspace/files")
async def list_workspace_files(
    path: str = Query("", description="Relative path from workspace root"),
    depth: int = Query(2, ge=1, le=5),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """List workspace directory structure. depth limits recursion."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path or ".")
    if resolved is None or not resolved.exists():
        raise HTTPException(status_code=400, detail="Invalid path")

    def _list_dir(p: Path, d: int) -> list[dict]:
        if d <= 0:
            return []
        items = []
        try:
            for child in sorted(p.iterdir()):
                name = child.name
                if name.startswith(".") and name != ".env":
                    continue
                rel = child.relative_to(workspace)
                item = {
                    "name": name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": child.is_dir(),
                }
                if child.is_dir() and d > 1:
                    item["children"] = _list_dir(child, d - 1)
                items.append(item)
        except PermissionError:
            pass
        return items

    return {"path": path or ".", "items": _list_dir(resolved, depth)}


@router.get("/workspace/file")
async def get_workspace_file(
    path: str = Query(..., description="Relative path from workspace root"),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Read a file from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"path": path, "content": content}


class WorkspaceFileUpdateRequest(BaseModel):
    path: str
    content: str


@router.put("/workspace/file")
async def update_workspace_file(
    request: WorkspaceFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Update a file in workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, request.path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        resolved.write_text(request.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "updated", "path": request.path}


BOT_FILE_KEYS = {
    "soul": "SOUL.md",
    "user": "USER.md",
    "heartbeat": "HEARTBEAT.md",
    "tools": "TOOLS.md",
    "agents": "AGENTS.md",
}


@router.get("/bot-files")
async def get_bot_files(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Get SOUL, USER, HEARTBEAT, TOOLS, AGENTS from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {
        "soul": _read_workspace_file(workspace, "SOUL.md"),
        "user": _read_workspace_file(workspace, "USER.md"),
        "heartbeat": _read_workspace_file(workspace, "HEARTBEAT.md"),
        "tools": _read_workspace_file(workspace, "TOOLS.md"),
        "agents": _read_workspace_file(workspace, "AGENTS.md"),
    }


class BotFileUpdateRequest(BaseModel):
    content: str


@router.put("/bot-files/{key}")
async def update_bot_file(
    key: str,
    request: BotFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Update a bot profile MD file (SOUL, USER, HEARTBEAT, TOOLS, AGENTS)."""
    if key not in BOT_FILE_KEYS:
        raise HTTPException(
            status_code=400, detail=f"Invalid key. Must be one of: {list(BOT_FILE_KEYS.keys())}"
        )
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    filename = BOT_FILE_KEYS[key]
    path = workspace / filename
    path.write_text(request.content, encoding="utf-8")
    return {"status": "updated", "key": key}


# ====================
# Config Endpoints
# ====================


@router.get("/config")
async def get_config(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get the full configuration."""
    state = _resolve_state(bot_id)
    return await state.get_config()


@router.put("/config")
async def update_config(
    request: ConfigUpdateRequest, bot_id: str | None = Query(None)
) -> dict[str, Any]:
    """Update configuration."""
    state = _resolve_state(bot_id)
    result = await state.update_config(request.section.value, request.data)

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return result


@router.get("/config/schema")
async def get_config_schema(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get the configuration schema."""
    state = _resolve_state(bot_id)
    return await state.get_config_schema()


@router.post("/config/validate")
async def validate_config(data: dict[str, Any], bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Validate configuration data."""
    state = _resolve_state(bot_id)
    return await state.validate_config(data)


# ====================
# Environment Variables Endpoints
# ====================


class EnvUpdateRequest(BaseModel):
    vars: dict[str, str] = {}


def _get_env_path(state) -> Path:
    """Get .env path for a bot state. Raises HTTPException if not available."""
    if state.bot_id == "_empty" or state.config_path is None:
        raise HTTPException(status_code=400, detail="No bot config path available")
    return state.config_path.parent / ".env"


@router.get("/env")
async def get_env(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get environment variables from the bot's .env file."""
    from dotenv import dotenv_values

    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    if not env_path.exists():
        return {"vars": {}}
    try:
        vars_dict = dotenv_values(env_path)
        return {"vars": {k: (v or "") for k, v in vars_dict.items()}}
    except Exception as e:
        logger.warning("Failed to read .env: {}", e)
        return {"vars": {}}


@router.put("/env")
async def update_env(request: EnvUpdateRequest, bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Update environment variables in the bot's .env file."""
    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for key, value in request.vars.items():
        if not key or "=" in key or "\n" in key:
            continue
        if not isinstance(value, str):
            value = str(value)
        if " " in value or "\n" in value or '"' in value or "=" in value or "#" in value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")

    try:
        env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write .env: {}", e)
        raise HTTPException(status_code=500, detail=f"Failed to save .env: {e}")

    return {"status": "ok", "vars": request.vars}


# ====================
# Skills Endpoints
# ====================


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str = ""


class SkillContentUpdateRequest(BaseModel):
    content: str


@router.get("/skills")
async def list_skills(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """List all skills (builtin + workspace) for a bot."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        return []

    from console.server.extension.skills import list_skills_for_bot

    skills = list_skills_for_bot(workspace)
    config = await state.get_config()
    skills_config = config.get("skills") or {}

    for s in skills:
        cfg = skills_config.get(s["name"])
        s["enabled"] = cfg.get("enabled", True) if isinstance(cfg, dict) else True

    return skills


@router.get("/skills/{name}/content")
async def get_skill_content(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Get skill content (read-only for builtin, editable for workspace)."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import get_skill_content as _get_content

    content = _get_content(workspace, name)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {"name": name, "content": content}


@router.post("/skills/{name}/copy-to-workspace")
async def copy_skill_to_workspace(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Copy a built-in skill to workspace, enabling editing."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import copy_builtin_skill_to_workspace

    if not copy_builtin_skill_to_workspace(workspace, name):
        raise HTTPException(
            status_code=400,
            detail="Skill already in workspace or not found",
        )
    return {"status": "copied", "name": name}


@router.put("/skills/{name}/content")
async def update_skill_content(
    name: str,
    request: SkillContentUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Update workspace skill content. Builtin skills are read-only."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import update_skill_content as _update_content

    content = request.content
    if not _update_content(workspace, name, content):
        raise HTTPException(
            status_code=400,
            detail="Skill not found or builtin (read-only)",
        )
    return {"status": "updated", "name": name}


@router.get("/skills/registry/search")
async def search_skills_registry(
    q: str = Query("", description="Search query"),
    registry_url: str | None = Query(None),
    bot_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Search skills in the registry."""
    from console.server.extension.skills_registry import search_registry

    config = {}
    if bot_id:
        state = _resolve_state(bot_id)
        config = await state.get_config()
    url = registry_url or config.get("console", {}).get("skills_registry_url")
    return search_registry(q or "", url)


class SkillInstallFromRegistryRequest(BaseModel):
    name: str
    registry_url: str | None = None


@router.post("/skills/install-from-registry")
async def install_skill_from_registry(
    request: SkillInstallFromRegistryRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Install a skill from the registry into workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills_registry import install_skill_from_registry as _install

    config = await state.get_config()
    url = request.registry_url or config.get("console", {}).get("skills_registry_url")
    ok = _install(request.name, workspace, url)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Skill not found in registry, already installed, or invalid name",
        )
    return {"status": "installed", "name": request.name}


@router.post("/skills")
async def create_skill(
    request: SkillCreateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Create a new workspace skill."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import create_workspace_skill

    if not create_workspace_skill(
        workspace,
        request.name,
        request.description,
        request.content,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid skill name or skill already exists",
        )
    return {"status": "created", "name": request.name}


@router.delete("/skills/{name}")
async def delete_skill(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Delete a workspace skill. Builtin skills cannot be deleted."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import delete_workspace_skill

    if not delete_workspace_skill(workspace, name):
        raise HTTPException(
            status_code=400,
            detail="Skill not found or builtin (cannot delete)",
        )
    return {"status": "deleted", "name": name}


# ====================
# Control Endpoints
# ====================


@router.post("/control/stop")
async def stop_current_task(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Stop the currently running task."""
    state = _resolve_state(bot_id)
    success = await state.stop_current_task()
    if not success:
        raise HTTPException(status_code=400, detail="No task running or unable to stop")

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "stopped"}


@router.post("/control/restart")
async def restart_bot(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Restart the bot."""
    state = _resolve_state(bot_id)
    success = await state.restart_bot()
    if not success:
        raise HTTPException(status_code=400, detail="Unable to restart")

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "restarting"}


# ====================
# Cron Endpoints
# ====================


def _cron_job_to_response(job) -> dict[str, Any]:
    """Convert CronJob to API response dict."""
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": job.schedule.kind,
            "at_ms": job.schedule.at_ms,
            "every_ms": job.schedule.every_ms,
            "expr": job.schedule.expr,
            "tz": job.schedule.tz,
        },
        "payload": {
            "kind": job.payload.kind,
            "message": job.payload.message,
            "deliver": job.payload.deliver,
            "channel": job.payload.channel,
            "to": job.payload.to,
        },
        "state": {
            "next_run_at_ms": job.state.next_run_at_ms,
            "last_run_at_ms": job.state.last_run_at_ms,
            "last_status": job.state.last_status,
            "last_error": job.state.last_error,
        },
        "created_at_ms": job.created_at_ms,
        "updated_at_ms": job.updated_at_ms,
        "delete_after_run": job.delete_after_run,
    }


@router.get("/cron", response_model=list[CronJobResponse])
async def list_cron_jobs(
    bot_id: str | None = Query(None),
    include_disabled: bool = Query(False),
) -> list[CronJobResponse]:
    """List all cron jobs."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        return []

    jobs = cron.list_jobs(include_disabled=include_disabled)
    return [CronJobResponse(**_cron_job_to_response(j)) for j in jobs]


@router.post("/cron", response_model=CronJobResponse)
async def add_cron_job(
    request: CronAddRequest,
    bot_id: str | None = Query(None),
) -> CronJobResponse:
    """Add a new cron job."""
    from nanobot.cron.types import CronSchedule

    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        raise HTTPException(status_code=503, detail="Cron service not available")

    schedule = CronSchedule(
        kind=request.schedule.kind.value,
        at_ms=request.schedule.at_ms,
        every_ms=request.schedule.every_ms,
        expr=request.schedule.expr,
        tz=request.schedule.tz,
    )
    job = cron.add_job(
        name=request.name,
        schedule=schedule,
        message=request.message,
        deliver=request.deliver,
        channel=request.channel,
        to=request.to,
        delete_after_run=request.delete_after_run,
    )
    return CronJobResponse(**_cron_job_to_response(job))


@router.delete("/cron/{job_id}")
async def remove_cron_job(
    job_id: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Remove a cron job."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        raise HTTPException(status_code=503, detail="Cron service not available")

    removed = cron.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


@router.put("/cron/{job_id}/enable")
async def enable_cron_job(
    job_id: str,
    enabled: bool = Query(True),
    bot_id: str | None = Query(None),
) -> CronJobResponse:
    """Enable or disable a cron job."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        raise HTTPException(status_code=503, detail="Cron service not available")

    job = cron.enable_job(job_id, enabled=enabled)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return CronJobResponse(**_cron_job_to_response(job))


@router.post("/cron/{job_id}/run")
async def run_cron_job(
    job_id: str,
    force: bool = Query(False),
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Manually run a cron job."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        raise HTTPException(status_code=503, detail="Cron service not available")

    ran = await cron.run_job(job_id, force=force)
    if not ran:
        raise HTTPException(status_code=404, detail="Job not found or disabled")
    return {"status": "ok", "job_id": job_id}


@router.get("/cron/status")
async def get_cron_status(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get cron service status."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        return {"enabled": False, "jobs": 0, "next_wake_at_ms": None}
    return cron.status()


@router.get("/cron/history")
async def get_cron_history(
    bot_id: str | None = Query(None),
    job_id: str | None = Query(None),
) -> dict[str, list[dict[str, Any]]]:
    """Get cron execution history per job."""
    state = _resolve_state(bot_id)
    from console.server.extension.cron_history import get_cron_history as _get_history

    return _get_history(state.bot_id, job_id)


# ====================
# Plans (Kanban Board)
# ====================


@router.get("/plans")
async def get_plans(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get Plans kanban board data."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        return {
            "id": "board-default",
            "name": "默认看板",
            "columns": [
                {"id": "col-backlog", "title": "待办", "order": 0},
                {"id": "col-progress", "title": "进行中", "order": 1},
                {"id": "col-done", "title": "已完成", "order": 2},
            ],
            "tasks": [],
        }
    from console.server.extension.plans import get_plans as _get_plans

    return _get_plans(state.bot_id)


class PlansSaveRequest(BaseModel):
    """Request body for saving plans board."""

    id: str
    name: str | None = None
    columns: list[dict[str, Any]]
    tasks: list[dict[str, Any]]


@router.put("/plans")
async def save_plans(
    request: PlansSaveRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Save Plans kanban board data."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")
    from console.server.extension.plans import save_plans as _save_plans

    data = {
        "id": request.id,
        "name": request.name,
        "columns": request.columns,
        "tasks": request.tasks,
    }
    _save_plans(state.bot_id, data)
    return data


class PlanTaskCreateRequest(BaseModel):
    """Request body for creating a task."""

    title: str
    description: str | None = None
    columnId: str = "col-backlog"
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    progress: int | None = None
    project: str | None = None


@router.post("/plans/tasks")
async def create_plan_task(
    request: PlanTaskCreateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Create a new task in Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans
    import time

    board = _get_plans(state.bot_id)
    now = time.time()

    # Generate task ID
    task_id = f"task-{int(now * 1000)}"

    new_task = {
        "id": task_id,
        "title": request.title,
        "description": request.description,
        "columnId": request.columnId,
        "order": len([t for t in board.get("tasks", []) if t.get("columnId") == request.columnId]),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if request.priority:
        new_task["priority"] = request.priority
    if request.startDate:
        new_task["startDate"] = request.startDate
    if request.dueDate:
        new_task["dueDate"] = request.dueDate
    if request.progress is not None:
        new_task["progress"] = request.progress
    if request.project:
        new_task["project"] = request.project

    tasks = board.get("tasks", [])
    tasks.append(new_task)
    board["tasks"] = tasks
    _save_plans(state.bot_id, board)

    return new_task


class PlanTaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    title: str | None = None
    description: str | None = None
    columnId: str | None = None
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    progress: int | None = None
    project: str | None = None


@router.put("/plans/tasks/{task_id}")
async def update_plan_task(
    task_id: str,
    request: PlanTaskUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Update an existing task in Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans

    board = _get_plans(state.bot_id)
    tasks = board.get("tasks", [])

    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update fields
    if request.title is not None:
        task["title"] = request.title
    if request.description is not None:
        task["description"] = request.description
    if request.columnId is not None:
        task["columnId"] = request.columnId
    if request.priority is not None:
        task["priority"] = request.priority
    if request.startDate is not None:
        task["startDate"] = request.startDate
    if request.dueDate is not None:
        task["dueDate"] = request.dueDate
    if request.progress is not None:
        task["progress"] = request.progress
    if request.project is not None:
        task["project"] = request.project

    import time

    task["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    board["tasks"] = tasks
    _save_plans(state.bot_id, board)

    return task


@router.delete("/plans/tasks/{task_id}")
async def delete_plan_task(
    task_id: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Delete a task from Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans

    board = _get_plans(state.bot_id)
    tasks = board.get("tasks", [])

    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    board["tasks"] = [t for t in tasks if t.get("id") != task_id]
    _save_plans(state.bot_id, board)

    return {"status": "deleted", "task_id": task_id}


# ====================
# Activity Feed
# ====================


@router.get("/activity")
async def get_activity_feed(
    bot_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    activity_type: str | None = Query(
        None, description="Filter by activity type: message, tool_call, channel, session, error"
    ),
) -> list[dict[str, Any]]:
    """Get activity feed with various event types."""
    from datetime import datetime

    state = _resolve_state(bot_id)

    if state.bot_id == "_empty":
        return []

    from console.server.extension.activity import get_activity as _get_activity

    activities = _get_activity(state.bot_id, limit=limit, activity_type=activity_type)

    result = []
    for entry in activities:
        ts = entry.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts)
            ts_str = dt.isoformat()
        else:
            ts_str = str(ts)

        data = entry.get("data") or {}
        entry_type = entry.get("type", "unknown")

        title = ""
        description = ""

        if entry_type == "tool_call":
            title = f"Tool: {data.get('tool_name', 'unknown')}"
            description = f"Status: {data.get('status', 'unknown')}"
        elif entry_type == "message":
            title = "Message received"
            content = data.get("content", "")
            description = content[:100] + "..." if len(content) > 100 else content
        elif entry_type == "channel":
            title = f"Channel: {data.get('channel', 'unknown')}"
            description = data.get("event", "event")
        elif entry_type == "session":
            title = f"Session: {data.get('action', 'unknown')}"
            description = data.get("session_key", "")
        elif entry_type == "error":
            title = "Error occurred"
            description = data.get("error", "Unknown error")[:100]

        result.append(
            {
                "id": entry.get("id", ""),
                "type": entry_type,
                "title": title,
                "description": description,
                "timestamp": ts_str,
                "metadata": data,
            }
        )

    return result


# ====================
# Alerts
# ====================


@router.get("/alerts")
async def get_alerts(
    bot_id: str | None = Query(None),
    include_dismissed: bool = Query(False),
) -> list[dict[str, Any]]:
    """Get alerts, with optional refresh from current status."""
    state = _resolve_state(bot_id)
    bid = state.bot_id
    if bid == "_empty":
        return []

    from console.server.extension.alerts import get_alerts as _get_alerts
    from console.server.extension.alerts import refresh_alerts
    from console.server.extension.usage import get_usage_today

    status = await state.get_status()
    usage_today = get_usage_today(bid)
    cron_jobs: list[dict[str, Any]] = []
    if state.cron_service:
        try:
            jobs = state.cron_service.list_jobs(include_disabled=True)
            for j in jobs:
                cron_jobs.append(
                    {
                        "id": j.id,
                        "name": j.name,
                        "enabled": j.enabled,
                        "state": {
                            "next_run_at_ms": j.state.next_run_at_ms,
                            "last_run_at_ms": j.state.last_run_at_ms,
                        },
                    }
                )
        except Exception:
            pass
    refresh_alerts(bid, status, cron_jobs, usage_today)
    return _get_alerts(bid, include_dismissed=include_dismissed)


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Dismiss an alert."""
    state = _resolve_state(bot_id)
    from console.server.extension.alerts import dismiss_alert as _dismiss

    ok = _dismiss(state.bot_id, alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "ok", "alert_id": alert_id}


# ====================
# Health Check
# ====================


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    from datetime import datetime

    from nanobot import __version__

    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/audit")
async def health_audit(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get health audit issues (bootstrap files, MCP config, channels, etc.)."""
    state = _resolve_state(bot_id)
    from console.server.extension.health import run_health_audit

    status = await state.get_status()
    config = await state.get_config()
    workspace = state.workspace
    issues = run_health_audit(state.bot_id, workspace, config, status)
    return {"issues": issues}

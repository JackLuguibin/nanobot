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
        result.append(BotInfoResponse(
            id=bot.id,
            name=bot.name,
            config_path=bot.config_path,
            workspace_path=bot.workspace_path,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            is_default=(bot.id == default_id),
            running=running,
        ))

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
    from nanobot.config.loader import load_config

    from console.server.bot_registry import get_registry
    from console.server.main import _initialize_bot

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.create_bot(request.name, request.source_config)

    try:
        config = load_config(Path(bot.config_path))
        state = _initialize_bot(bot.id, config, Path(bot.config_path))
        manager.set_state(bot.id, state)
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
    if old_state and old_state.agent_loop:
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


# ====================
# Status Endpoints
# ====================


@router.get("/status", response_model=StatusResponse)
async def get_status(bot_id: str | None = Query(None)) -> StatusResponse:
    """Get the overall bot status."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return StatusResponse(**status)


@router.get("/channels", response_model=list[ChannelStatus])
async def get_channels(bot_id: str | None = Query(None)) -> list[ChannelStatus]:
    """Get all channel statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [ChannelStatus(**ch) for ch in status.get("channels", [])]


@router.get("/mcp", response_model=list[MCPStatus])
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


@router.get("/tools/log", response_model=list[ToolCallLog])
async def get_tool_logs(
    limit: int = 50,
    tool_name: str | None = None,
    bot_id: str | None = Query(None),
) -> list[ToolCallLog]:
    """Get tool call logs."""
    state = _resolve_state(bot_id)
    logs = state.tool_call_logs

    if tool_name:
        logs = [log for log in logs if log.get("tool_name") == tool_name]

    logs = logs[-limit:]

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
        await manager.broadcast_status_update(status)
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
        await manager.broadcast_status_update(status)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "deleted", "key": key}


# ====================
# Chat Endpoints
# ====================


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(request: ChatRequest) -> ChatResponse:
    """Send a chat message and get a response."""
    state = _resolve_state(request.bot_id)
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(
            status_code=503, detail="Agent not running. Please configure an API key in your config."
        )

    session_key = request.session_key
    if session_key is None:
        session = await state.create_session()
        session_key = session["key"]

    try:
        async def silent_progress(content: str) -> None:
            pass

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
    state = _resolve_state(request.bot_id)
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(
            status_code=503, detail="Agent not running. Please configure an API key in your config."
        )

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

            async def stream_progress(content: str, *, tool_hint: bool = False) -> None:
                await queue.put(f"data: {json.dumps({'type': 'chat_token', 'content': content})}\n\n")

            async def run_agent() -> None:
                try:
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
                    await queue.put(None)

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
                await manager.broadcast_status_update(status)
            except Exception as e:
                logger.warning("Failed to broadcast status update: {}", e)

            response_text = response_holder[0] if response_holder else ""
            yield f"data: {json.dumps({'type': 'chat_done', 'done': True, 'content': response_text})}\n\n"

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
# Config Endpoints
# ====================


@router.get("/config")
async def get_config(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get the full configuration."""
    state = _resolve_state(bot_id)
    return await state.get_config()


@router.put("/config")
async def update_config(request: ConfigUpdateRequest, bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Update configuration."""
    state = _resolve_state(bot_id)
    result = await state.update_config(request.section.value, request.data)

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status)
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
        await manager.broadcast_status_update(status)
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
        await manager.broadcast_status_update(status)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "restarting"}


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

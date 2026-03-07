"""API routes for the console server."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from loguru import logger

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
from console.server.api.state import get_state
from console.server.api.websocket import get_connection_manager, handle_websocket

# Create router
router = APIRouter(prefix="/api")


# ====================
# Status Endpoints
# ====================


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get the overall bot status."""
    state = get_state()
    status = await state.get_status()
    return StatusResponse(**status)


@router.get("/channels", response_model=list[ChannelStatus])
async def get_channels() -> list[ChannelStatus]:
    """Get all channel statuses."""
    state = get_state()
    status = await state.get_status()
    return [ChannelStatus(**ch) for ch in status.get("channels", [])]


@router.get("/mcp", response_model=list[MCPStatus])
async def get_mcp_servers() -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = get_state()
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


@router.get("/tools/log", response_model=list[ToolCallLog])
async def get_tool_logs(
    limit: int = 50,
    tool_name: str | None = None,
) -> list[ToolCallLog]:
    """Get tool call logs."""
    state = get_state()
    logs = state.tool_call_logs

    # Filter by tool name if specified
    if tool_name:
        logs = [log for log in logs if log.get("tool_name") == tool_name]

    # Limit results
    logs = logs[-limit:]

    return [ToolCallLog(**log) for log in logs]


# ====================
# Session Endpoints
# ====================


@router.get("/sessions")
async def list_sessions() -> list[SessionInfo]:
    """List all sessions."""
    state = get_state()
    sessions = await state.get_sessions()
    return [SessionInfo(**s) for s in sessions]


@router.get("/sessions/{key}")
async def get_session(key: str) -> dict[str, Any]:
    """Get a specific session with full history."""
    state = get_state()
    session = await state.get_session(key)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions")
async def create_session(key: str | None = None) -> SessionInfo:
    """Create a new session."""
    state = get_state()
    session = await state.create_session(key)

    # Broadcast status update to all WebSocket clients
    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return SessionInfo(**session)


@router.delete("/sessions/{key}")
async def delete_session(key: str) -> dict[str, str]:
    """Delete a session."""
    state = get_state()
    deleted = await state.delete_session(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    # Broadcast status update to all WebSocket clients
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
    state = get_state()
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(
            status_code=503, detail="Agent not running. Please configure an API key in your config."
        )

    # Get or create session
    session_key = request.session_key
    if session_key is None:
        session = await state.create_session()
        session_key = session["key"]

    # Process the message through the agent
    try:
        # Use agent.process_direct for direct message processing
        async def silent_progress(content: str) -> None:
            pass

        response = await agent_loop.process_direct(
            content=request.message,
            session_key=session_key,
            channel="console",
            chat_id="web",
            on_progress=silent_progress,
        )

        # Increment message counter
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
    state = get_state()
    agent_loop = state.agent_loop

    if agent_loop is None:
        raise HTTPException(
            status_code=503, detail="Agent not running. Please configure an API key in your config."
        )

    # Get or create session
    session_key = request.session_key
    if session_key is None:
        session = await state.create_session()
        session_key = session["key"]

    async def generate():
        try:
            # Send initial session key
            yield f"data: {json.dumps({'type': 'session_key', 'session_key': session_key})}\n\n"

            # Track accumulated response for tool call handling
            accumulated_response = []

            # Define progress callback to stream tokens
            async def stream_progress(content: str) -> None:
                yield f"data: {json.dumps({'type': 'chat_token', 'content': content})}\n\n"
                accumulated_response.append(content)

            # Process the message through the agent
            await agent_loop.process_direct(
                content=request.message,
                session_key=session_key,
                channel="console",
                chat_id="web",
                on_progress=stream_progress,
            )

            # Increment message counter
            state.increment_messages()

            # Broadcast status update to all WebSocket clients
            try:
                manager = get_connection_manager()
                status = await state.get_status()
                await manager.broadcast_status_update(status)
            except Exception as e:
                logger.warning("Failed to broadcast status update: {}", e)

            # Send done message
            yield f"data: {json.dumps({'type': 'chat_done', 'done': True})}\n\n"

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
async def get_config() -> dict[str, Any]:
    """Get the full configuration."""
    state = get_state()
    return await state.get_config()


@router.put("/config")
async def update_config(request: ConfigUpdateRequest) -> dict[str, Any]:
    """Update configuration."""
    state = get_state()
    result = await state.update_config(request.section.value, request.data)

    # Broadcast status update to all WebSocket clients (config change may affect status)
    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return result


@router.get("/config/schema")
async def get_config_schema() -> dict[str, Any]:
    """Get the configuration schema."""
    state = get_state()
    return await state.get_config_schema()


@router.post("/config/validate")
async def validate_config(data: dict[str, Any]) -> dict[str, Any]:
    """Validate configuration data."""
    state = get_state()
    return await state.validate_config(data)


# ====================
# Control Endpoints
# ====================


@router.post("/control/stop")
async def stop_current_task() -> dict[str, str]:
    """Stop the currently running task."""
    state = get_state()
    success = await state.stop_current_task()
    if not success:
        raise HTTPException(status_code=400, detail="No task running or unable to stop")

    # Broadcast status update to all WebSocket clients
    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return {"status": "stopped"}


@router.post("/control/restart")
async def restart_bot() -> dict[str, str]:
    """Restart the bot."""
    state = get_state()
    success = await state.restart_bot()
    if not success:
        raise HTTPException(status_code=400, detail="Unable to restart")

    # Broadcast status update to all WebSocket clients
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

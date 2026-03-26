"""API routes for health checks and control operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state

router = APIRouter(prefix="/health")


@router.get("", response_model=dict)
async def health_check() -> dict:
    """Health check endpoint."""
    from nanobot import __version__

    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/audit")
async def health_audit(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get health audit issues (bootstrap files, MCP config, channels, etc.)."""
    state = get_state(bot_id)
    from console.server.extension.health import run_health_audit

    status = await state.get_status()
    config = await state.get_config()
    workspace = state.workspace
    issues = run_health_audit(state.bot_id, workspace, config, status)
    return {"issues": issues}


control_router = APIRouter(prefix="/control")


@control_router.post("/stop")
async def stop_current_task(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Stop the currently running task."""
    from console.server.api.websocket import get_connection_manager

    state = get_state(bot_id)
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


@control_router.post("/restart")
async def restart_bot(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Restart the bot."""
    from console.server.api.websocket import get_connection_manager

    state = get_state(bot_id)
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

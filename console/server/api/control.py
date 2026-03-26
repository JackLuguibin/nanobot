"""API routes for bot control operations (stop / restart)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state

router = APIRouter(prefix="/control")


@router.post("/stop")
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


@router.post("/restart")
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

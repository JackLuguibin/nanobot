"""API routes for session management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from console.server.models.base import SessionInfo
from console.server.api.state import get_state
from console.server.api.websocket import get_connection_manager

router = APIRouter(prefix="/api/sessions")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SessionInfo])
async def list_sessions(bot_id: str | None = Query(None)) -> list[SessionInfo]:
    """List all sessions."""
    state = _resolve_state(bot_id)
    sessions = await state.get_sessions()
    return [SessionInfo(**s) for s in sessions]


@router.get("/{key}")
async def get_session(key: str, bot_id: str | None = Query(None)) -> dict:
    """Get a specific session with full history."""
    state = _resolve_state(bot_id)
    session = await state.get_session(key)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("", response_model=SessionInfo)
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


@router.delete("/{key}")
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

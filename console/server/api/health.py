"""API routes for health checks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
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


control_router = None  # moved to console.server.api.control

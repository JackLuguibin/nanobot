"""API routes for health checks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from console.server.api.state import get_state
from console.server.models.activity import HealthResponse
from console.server.models.health import HealthAuditIssue, HealthAuditResponse

router = APIRouter(prefix="/health")


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    from nanobot import __version__

    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/audit", response_model=HealthAuditResponse)
async def health_audit(bot_id: str | None = Query(None)) -> HealthAuditResponse:
    """Get health audit issues (bootstrap files, MCP config, channels, etc.)."""
    state = get_state(bot_id)
    from console.server.extension.health import run_health_audit

    status = await state.get_status()
    config = await state.get_config()
    workspace = state.workspace
    raw_issues = run_health_audit(state.bot_id, workspace, config, status)
    issues = [HealthAuditIssue(**issue) for issue in raw_issues]
    return HealthAuditResponse(issues=issues)

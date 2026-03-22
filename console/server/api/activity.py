"""API routes for activity feed, alerts and health checks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from console.server.api.state import get_state

router = APIRouter(prefix="/api")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Activity Feed
# ---------------------------------------------------------------------------


@router.get("/activity")
async def get_activity_feed(
    bot_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    activity_type: str | None = Query(
        None, description="Filter by activity type: message, tool_call, channel, session, error"
    ),
) -> list[dict[str, Any]]:
    """Get activity feed with various event types."""
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


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


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
        except Exception as e:
            logger.debug("Failed to serialize cron job '{}': {}", j.id, e)
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


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    from nanobot import __version__

    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.utcnow().isoformat(),
    )


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


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------


@router.post("/control/stop")
async def stop_current_task(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Stop the currently running task."""
    from console.server.api.websocket import get_connection_manager

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
    from console.server.api.websocket import get_connection_manager

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

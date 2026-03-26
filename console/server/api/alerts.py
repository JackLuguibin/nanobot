"""API routes for alerts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state

router = APIRouter(prefix="/alerts")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("")
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


@router.post("/{alert_id}/dismiss")
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

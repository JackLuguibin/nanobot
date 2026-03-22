"""API routes for cron (scheduled tasks) management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from console.server.models.cron import CronAddRequest, CronJobResponse
from console.server.api.state import get_state

router = APIRouter(prefix="/api/cron")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


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


@router.get("", response_model=list[CronJobResponse])
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


@router.post("", response_model=CronJobResponse)
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


@router.delete("/{job_id}")
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


@router.put("/{job_id}/enable")
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


@router.post("/{job_id}/run")
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


@router.get("/status")
async def get_cron_status(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get cron service status."""
    state = _resolve_state(bot_id)
    cron = state.cron_service
    if cron is None:
        return {"enabled": False, "jobs": 0, "next_wake_at_ms": None}
    return cron.status()


@router.get("/history")
async def get_cron_history(
    bot_id: str | None = Query(None),
    job_id: str | None = Query(None),
) -> dict[str, list[dict[str, Any]]]:
    """Get cron execution history per job."""
    state = _resolve_state(bot_id)
    from console.server.extension.cron_history import get_cron_history as _get_history

    return _get_history(state.bot_id, job_id)

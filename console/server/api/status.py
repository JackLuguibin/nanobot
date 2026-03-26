"""API routes for status and monitoring."""

from __future__ import annotations

from fastapi import APIRouter, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.models.system import StatusResponse

router = APIRouter(prefix="/status")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=StatusResponse)
async def get_status(bot_id: str | None = Query(None)) -> StatusResponse:
    """Get the overall bot status."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return StatusResponse(**status)

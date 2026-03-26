"""API routes for channel management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.models.base import ChannelStatus
from console.server.models.status import ChannelUpdateRequest

router = APIRouter(prefix="/channels")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[ChannelStatus])
async def get_channels(bot_id: str | None = Query(None)) -> list[ChannelStatus]:
    """Get all channels from config, merged with runtime status when available."""
    state = _resolve_state(bot_id)
    channels = await state.get_channels()
    return [ChannelStatus(**ch) for ch in channels]


@router.put("/{name}")
async def update_channel(
    name: str,
    request: ChannelUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Update a channel's configuration."""
    state = _resolve_state(bot_id)
    try:
        return await state.update_channel(name, request.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}")
async def delete_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Disable a channel (set enabled=False)."""
    state = _resolve_state(bot_id)
    ok = await state.delete_channel(name)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {name}")
    return {"status": "ok"}


@router.post("/{name}/refresh")
async def refresh_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Stop and restart a specific channel."""
    state = _resolve_state(bot_id)
    return await state.refresh_channel(name)


@router.post("/refresh")
async def refresh_all_channels(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """Stop and restart all running channels."""
    state = _resolve_state(bot_id)
    return await state.refresh_all_channels()

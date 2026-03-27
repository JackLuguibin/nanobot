"""API routes for channel management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.status import ChannelStatus
from console.server.models.status import (
    AllChannelsRefreshResponse,
    ChannelDeleteResponse,
    ChannelRefreshResponse,
    ChannelUpdateRequest,
    ChannelUpdateResponse,
)

router = APIRouter(prefix="/channels")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[ChannelStatus])
async def get_channels(bot_id: str | None = Query(None)) -> list[ChannelStatus]:
    """Get all channels from config, merged with runtime status when available."""
    state = _resolve_state(bot_id)
    channels = await state.get_channels()
    return [ChannelStatus(**ch) for ch in channels]


@router.put("/{name}", response_model=ChannelUpdateResponse)
async def update_channel(
    name: str,
    request: ChannelUpdateRequest,
    bot_id: str | None = Query(None),
) -> ChannelUpdateResponse:
    """Update a channel's configuration."""
    state = _resolve_state(bot_id)
    try:
        raw = await state.update_channel(name, request.data)
        return ChannelUpdateResponse(data=raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}", response_model=ChannelDeleteResponse)
async def delete_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> ChannelDeleteResponse:
    """Disable a channel (set enabled=False)."""
    state = _resolve_state(bot_id)
    ok = await state.delete_channel(name)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {name}")
    return ChannelDeleteResponse()


@router.post("/{name}/refresh", response_model=ChannelRefreshResponse)
async def refresh_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> ChannelRefreshResponse:
    """Stop and restart a specific channel."""
    state = _resolve_state(bot_id)
    raw = await state.refresh_channel(name)
    return ChannelRefreshResponse(**raw)


@router.post("/refresh", response_model=AllChannelsRefreshResponse)
async def refresh_all_channels(bot_id: str | None = Query(None)) -> AllChannelsRefreshResponse:
    """Stop and restart all running channels."""
    state = _resolve_state(bot_id)
    raws = await state.refresh_all_channels()
    results = [ChannelRefreshResponse(**raw) for raw in raws]
    return AllChannelsRefreshResponse(results=results)

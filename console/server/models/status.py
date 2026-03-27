"""Session and channel status models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .base import ChannelStatus


class ChannelUpdateRequest(BaseModel):
    """Request body for updating a channel."""

    data: dict[str, Any]


class ChannelUpdateResponse(BaseModel):
    """Response body for PUT /channels/{name}."""

    data: dict[str, Any]


class ChannelDeleteResponse(BaseModel):
    """Response body for DELETE /channels/{name}."""

    status: str = "ok"


class ChannelRefreshResponse(BaseModel):
    """Response body for POST /channels/{name}/refresh."""

    name: str
    success: bool
    message: str | None = None


class AllChannelsRefreshResponse(BaseModel):
    """Response body for POST /channels/refresh."""

    results: list[ChannelRefreshResponse]

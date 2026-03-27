"""Status and session-info models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import MessageRole


class SessionInfo(BaseModel):
    key: str
    title: str | None = None
    message_count: int
    last_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChannelStatus(BaseModel):
    name: str
    enabled: bool
    status: str  # "online", "offline", "error"
    stats: dict[str, Any] = Field(default_factory=dict)


class MCPStatus(BaseModel):
    name: str
    status: str  # "connected", "disconnected", "error"
    server_type: str  # "stdio", "http"
    last_connected: datetime | None = None
    error: str | None = None


class ToolCallLog(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    result: str | None = None
    status: str  # "success", "error"
    duration_ms: float
    timestamp: datetime


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

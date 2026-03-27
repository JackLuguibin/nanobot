"""System status and health models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .status import ChannelStatus, MCPStatus
from .usage import TokenUsageResponse


class StatusResponse(BaseModel):
    running: bool
    uptime_seconds: float
    model: str | None
    active_sessions: int
    messages_today: int
    token_usage: TokenUsageResponse = Field(default_factory=TokenUsageResponse)
    channels: list[ChannelStatus]
    mcp_servers: list[MCPStatus]


class HealthCheck(BaseModel):
    status: str
    version: str
    timestamp: datetime

"""Session and channel status models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .base import ChannelStatus, MCPStatus, SessionInfo, ToolCallLog


class ChannelUpdateRequest(BaseModel):
    """Request body for updating a channel."""

    data: dict[str, Any]

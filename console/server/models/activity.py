"""Activity feed models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ActivityEntryType(str, Enum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    CHANNEL = "channel"
    SESSION = "session"
    ERROR = "error"


class ActivityEntry(BaseModel):
    """Single activity feed entry."""

    id: str
    type: ActivityEntryType
    title: str
    description: str | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: str

"""Alert models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AlertCategory(str, Enum):
    CHANNEL = "channel"
    AGENT = "agent"
    CONFIG = "config"
    USAGE = "usage"
    MCP = "mcp"
    CRON = "cron"
    SYSTEM = "system"


class AlertItem(BaseModel):
    """Single alert item returned by GET /alerts."""

    id: str
    title: str
    message: str
    severity: AlertSeverity
    category: AlertCategory
    dismissed: bool = False
    created_at: datetime | None = None
    data: dict[str, Any] | None = None


class AlertDismissRequest(BaseModel):
    """Request body for dismissing an alert (query param for route, kept for consistency)."""

    alert_id: str


class AlertDismissResponse(BaseModel):
    """Response body after dismissing an alert."""

    status: str = "ok"
    alert_id: str

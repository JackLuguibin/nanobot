"""Health check and audit models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class HealthIssueSeverity(str, Enum):
    """Severity levels matching extension/health.py: critical, warning, info."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class HealthAuditIssue(BaseModel):
    """Single health audit issue.

    Fields match the actual output of extension/health.run_health_audit():
      { type, severity, message, bot_id?, path?, metadata? }
    """

    type: str  # e.g. "bootstrap_missing", "no_channels", "mcp_config_error"
    severity: HealthIssueSeverity
    message: str
    bot_id: str | None = None
    path: str | None = None
    metadata: dict[str, Any] | None = None


class HealthAuditResponse(BaseModel):
    """Response body for GET /health/audit."""

    issues: list[HealthAuditIssue]

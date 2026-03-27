"""Bot control operation models."""

from __future__ import annotations

from pydantic import BaseModel


class StopResponse(BaseModel):
    """Response body for POST /control/stop."""

    status: str = "stopped"


class RestartResponse(BaseModel):
    """Response body for POST /control/restart."""

    status: str = "restarting"

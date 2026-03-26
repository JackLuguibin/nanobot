"""Environment variable models."""

from __future__ import annotations

from pydantic import BaseModel


class EnvVarsResponse(BaseModel):
    """GET /api/v1/env response."""

    vars: dict[str, str] = {}


class EnvUpdateRequest(BaseModel):
    """PUT /api/v1/env request body."""

    vars: dict[str, str] = {}


class EnvUpdateResponse(BaseModel):
    """PUT /api/v1/env response."""

    status: str = "ok"
    vars: dict[str, str] = {}

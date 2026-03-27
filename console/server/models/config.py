"""Configuration models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .enums import ConfigSection


class ConfigUpdateRequest(BaseModel):
    section: ConfigSection
    data: dict[str, Any]


class ConfigValidateResponse(BaseModel):
    """Response for POST /config/validate."""

    valid: bool
    errors: list[str]

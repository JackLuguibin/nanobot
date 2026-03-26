"""Configuration models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .base import ConfigSection


class ConfigUpdateRequest(BaseModel):
    section: ConfigSection
    data: dict[str, Any]

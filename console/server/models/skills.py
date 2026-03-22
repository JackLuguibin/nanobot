"""Skills management models."""

from __future__ import annotations

from pydantic import BaseModel


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str = ""


class SkillContentUpdateRequest(BaseModel):
    content: str


class SkillInstallFromRegistryRequest(BaseModel):
    name: str
    registry_url: str | None = None

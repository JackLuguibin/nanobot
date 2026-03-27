"""Skills management models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SkillInfo(BaseModel):
    """Single skill item returned by GET /skills."""

    name: str
    description: str | None = None
    path: str | None = None
    builtin: bool = False
    workspace: bool = False
    enabled: bool = True


class SkillContentResponse(BaseModel):
    """Response body for GET /skills/{name}/content."""

    name: str
    content: str


class SkillCopyResponse(BaseModel):
    """Response body for POST /skills/{name}/copy-to-workspace."""

    status: str = "copied"
    name: str


class SkillUpdateResponse(BaseModel):
    """Response body for PUT /skills/{name}/content."""

    status: str = "updated"
    name: str


class SkillInstallResponse(BaseModel):
    """Response body for POST /skills/install-from-registry."""

    status: str = "installed"
    name: str


class SkillCreateResponse(BaseModel):
    """Response body for POST /skills."""

    status: str = "created"
    name: str


class SkillDeleteResponse(BaseModel):
    """Response body for DELETE /skills/{name}."""

    status: str = "deleted"
    name: str


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str = ""


class SkillContentUpdateRequest(BaseModel):
    content: str


class SkillInstallFromRegistryRequest(BaseModel):
    name: str
    registry_url: str | None = None

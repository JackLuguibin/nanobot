"""Workspace and bot-files models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WorkspaceFileUpdateRequest(BaseModel):
    path: str
    content: str


class BotFileUpdateRequest(BaseModel):
    content: str


class WorkspaceFileItem(BaseModel):
    """Single file or directory entry in workspace listing."""

    name: str
    path: str
    is_dir: bool
    children: list["WorkspaceFileItem"] | None = None


class WorkspaceFileListResponse(BaseModel):
    """Response for GET /workspace/files."""

    path: str
    items: list[WorkspaceFileItem]


class WorkspaceFileReadResponse(BaseModel):
    """Response for GET /workspace/file."""

    path: str
    content: str


class WorkspaceFileUpdateResponse(BaseModel):
    """Response for PUT /workspace/file."""

    status: str = "updated"
    path: str


class BotFilesResponse(BaseModel):
    """Response for GET /bot-files (all bot files at once)."""

    soul: str = ""
    user: str = ""
    heartbeat: str = ""
    tools: str = ""
    agents: str = ""


class BotFileUpdateResponse(BaseModel):
    """Response for PUT /bot-files/{key}."""

    status: str = "updated"
    key: str

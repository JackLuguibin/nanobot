"""Workspace and bot-files models."""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceFileUpdateRequest(BaseModel):
    path: str
    content: str


class BotFileUpdateRequest(BaseModel):
    content: str

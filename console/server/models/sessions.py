"""Session management models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .base import MessageRole, SessionInfo


class SessionMessage(BaseModel):
    """Single message within a session."""

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    timestamp: str | None = None
    source: str | None = None


class GetSessionResponse(BaseModel):
    """Full session response with message history (GET /sessions/{key})."""

    key: str
    title: str
    messages: list[SessionMessage]
    message_count: int


class CreateSessionResponse(BaseModel):
    """Response after creating a session (POST /sessions)."""

    key: str
    title: str
    message_count: int


class DeleteSessionResponse(BaseModel):
    """Response after deleting a session (DELETE /sessions/{key})."""

    status: str = "deleted"
    key: str

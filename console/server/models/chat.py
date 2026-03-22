"""Chat / message models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .base import MessageRole


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    session_key: str | None = None
    message: str
    stream: bool = False
    bot_id: str | None = None


class ChatResponse(BaseModel):
    session_key: str
    message: str
    tool_calls: list[ToolCall] | None = None
    done: bool = True


class WSMessage(BaseModel):
    type: Any  # WSMessageType
    data: Any
    session_key: str | None = None

"""Pydantic models for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


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


class SessionInfo(BaseModel):
    key: str
    title: str | None = None
    message_count: int
    last_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChannelStatus(BaseModel):
    name: str
    enabled: bool
    status: str  # "online", "offline", "error"
    stats: dict[str, Any] = Field(default_factory=dict)


class MCPStatus(BaseModel):
    name: str
    status: str  # "connected", "disconnected", "error"
    server_type: str  # "stdio", "http"
    last_connected: datetime | None = None
    error: str | None = None


class ToolCallLog(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    result: str | None = None
    status: str  # "success", "error"
    duration_ms: float
    timestamp: datetime


class ConfigSection(str, Enum):
    GENERAL = "general"
    PROVIDERS = "providers"
    TOOLS = "tools"
    CHANNELS = "channels"
    SKILLS = "skills"


class ConfigUpdateRequest(BaseModel):
    section: ConfigSection
    data: dict[str, Any]


class StatusResponse(BaseModel):
    running: bool
    uptime_seconds: float
    model: str | None
    active_sessions: int
    messages_today: int
    channels: list[ChannelStatus]
    mcp_servers: list[MCPStatus]


class WSMessageType(str, Enum):
    CHAT_TOKEN = "chat_token"
    CHAT_DONE = "chat_done"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_PROGRESS = "tool_progress"
    ERROR = "error"
    STATUS_UPDATE = "status_update"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Any
    session_key: str | None = None


class HealthCheck(BaseModel):
    status: str
    version: str
    timestamp: datetime

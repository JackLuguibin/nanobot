"""Base API models: response wrappers, error codes, shared enums."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# ====================
# 统一响应码与信封
# ====================

API_CODE_SUCCESS = 0


class ApiErrorCode:
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE = 422
    SERVICE_UNAVAILABLE = 503
    INTERNAL_ERROR = 500


class ApiSuccessResponse(BaseModel, Generic[T]):
    """成功响应信封：code=0, message, data"""

    code: int = Field(default=API_CODE_SUCCESS, description="成功时为 0")
    message: str = Field(default="success", description="成功描述")
    data: Any = None


class ApiErrorResponse(BaseModel):
    """错误响应：code 为错误码，message 为错误原因"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误原因，供前端直接展示")


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConfigSection(str, Enum):
    GENERAL = "general"
    AGENTS = "agents"
    PROVIDERS = "providers"
    TOOLS = "tools"
    CHANNELS = "channels"
    SKILLS = "skills"


class WSMessageType(str, Enum):
    CHAT_TOKEN = "chat_token"
    CHAT_DONE = "chat_done"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_PROGRESS = "tool_progress"
    ERROR = "error"
    STATUS_UPDATE = "status_update"
    SESSIONS_UPDATE = "sessions_update"
    BOTS_UPDATE = "bots_update"
    QUEUE_UPDATE = "queue_update"


# ====================
# Shared status / session models (moved here to break circular imports)
# ====================


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

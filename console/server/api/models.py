"""Pydantic models for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# ====================
# 统一响应码与信封
# ====================

# 成功码
API_CODE_SUCCESS = 0

# 错误码（与 HTTP 状态码对齐，便于前端识别；业务错误可使用 4xx 段）
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
    AGENTS = "agents"
    PROVIDERS = "providers"
    TOOLS = "tools"
    CHANNELS = "channels"
    SKILLS = "skills"


class ConfigUpdateRequest(BaseModel):
    section: ConfigSection
    data: dict[str, Any]


class TokenUsageResponse(BaseModel):
    """当日 token 使用量与成本，与 extension.usage.get_usage_today 返回结构一致。"""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_by_model: dict[str, float] = Field(default_factory=dict)


class StatusResponse(BaseModel):
    running: bool
    uptime_seconds: float
    model: str | None
    active_sessions: int
    messages_today: int
    token_usage: TokenUsageResponse = Field(default_factory=TokenUsageResponse)
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
    SESSIONS_UPDATE = "sessions_update"
    BOTS_UPDATE = "bots_update"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Any
    session_key: str | None = None


class HealthCheck(BaseModel):
    status: str
    version: str
    timestamp: datetime


# Cron API models
class CronScheduleKind(str, Enum):
    AT = "at"
    EVERY = "every"
    CRON = "cron"


class CronScheduleInput(BaseModel):
    kind: CronScheduleKind
    at_ms: int | None = None
    every_ms: int | None = None
    expr: str | None = None
    tz: str | None = None


class CronAddRequest(BaseModel):
    name: str
    schedule: CronScheduleInput
    message: str = ""
    deliver: bool = False
    channel: str | None = None
    to: str | None = None
    delete_after_run: bool = False


class CronJobResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    schedule: dict[str, Any]
    payload: dict[str, Any]
    state: dict[str, Any]
    created_at_ms: int
    updated_at_ms: int
    delete_after_run: bool

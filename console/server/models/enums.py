"""Shared Pydantic enums used across the API layer."""

from __future__ import annotations

from enum import Enum


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

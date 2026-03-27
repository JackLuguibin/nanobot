"""Multi-agent models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    key: str
    label: str
    color: str


class CategoryCreateRequest(BaseModel):
    label: str


class CategoryOverrideRequest(BaseModel):
    agent_id: str
    category_key: str | None  # None = clear override


class AgentCreateRequest(BaseModel):
    """Request body for creating an Agent."""

    id: str | None = None
    name: str
    description: str | None = None
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    skills: list[str] = []
    topics: list[str] = []
    collaborators: list[str] = []
    enabled: bool = True
    display_category: str | None = None


class AgentUpdateRequest(BaseModel):
    """Request body for updating an Agent."""

    name: str | None = None
    description: str | None = None
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    skills: list[str] | None = None
    topics: list[str] | None = None
    collaborators: list[str] | None = None
    enabled: bool | None = None
    display_category: str | None = None  # None = keep existing


class AgentResponse(BaseModel):
    """Response body for an Agent."""

    id: str
    name: str
    description: str | None
    model: str | None
    temperature: float | None
    system_prompt: str | None
    skills: list[str]
    topics: list[str]
    collaborators: list[str]
    enabled: bool
    created_at: str


class DelegateTaskRequest(BaseModel):
    to_agent_id: str
    task: str
    context: dict[str, Any] = {}
    wait_response: bool = False


class DelegateTaskResponse(BaseModel):
    correlation_id: str
    response: str | None


class BroadcastEventRequest(BaseModel):
    topic: str
    content: str
    context: dict[str, Any] = {}


class BroadcastEventResponse(BaseModel):
    """Response for POST /{agent_id}/broadcast."""

    status: str = "broadcasted"
    topic: str


class CategoryDeleteResponse(BaseModel):
    """Response for DELETE /categories/{category_key}."""

    status: str = "deleted"
    key: str


class AgentDeleteResponse(BaseModel):
    """Response for DELETE /{agent_id}."""

    status: str = "deleted"
    agent_id: str


class AgentStatusResponse(BaseModel):
    """Agent or system status response (GET /{agent_id}/status)."""

    total_agents: int = 0
    enabled_agents: int = 0
    subscribed_agents: list[str] = []
    zmq_initialized: bool = False
    agent_id: str | None = None
    agent_name: str | None = None
    enabled: bool | None = None
    bot_id: str | None = None
    full_agent_id: str | None = None

"""API routes for multi-agent management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from console.server.api.state import get_state_manager
from console.server.extension.agents import AgentConfig, AgentManager
from console.server.models.agents import (
    AgentCreateRequest,
    AgentResponse,
    AgentUpdateRequest,
    BroadcastEventRequest,
    CategoryCreateRequest,
    CategoryOverrideRequest,
    CategoryResponse,
    DelegateTaskRequest,
    DelegateTaskResponse,
)

router = APIRouter(prefix="/bots/{bot_id}/agents")


def _get_agent_manager_optional(bot_id: str) -> AgentManager | None:
    """Get the Bot's AgentManager instance. Returns None if not initialized."""
    state_manager = get_state_manager()
    state = state_manager.get_state(bot_id)
    if not hasattr(state, "_agent_manager") or state._agent_manager is None:
        return None
    return state._agent_manager


def _resolve_agent_manager(bot_id: str) -> AgentManager:
    """Get the Bot's AgentManager instance. Raises 404 if not initialized."""
    manager = _get_agent_manager_optional(bot_id)
    if manager is None:
        logger.warning(f"Agent system not initialized for bot '{bot_id}'")
        raise HTTPException(
            status_code=404, detail=f"Agent system not initialized for bot '{bot_id}'"
        )
    return manager


# ---------------------------------------------------------------------------
# Category endpoints
# ---------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(bot_id: str) -> list[CategoryResponse]:
    """List all custom categories for a bot."""
    manager = _get_agent_manager_optional(bot_id)
    if manager is None:
        return []
    cats = manager.category_manager.list_categories()
    return [CategoryResponse(key=c.key, label=c.label, color=c.color) for c in cats]


@router.post("/categories", response_model=CategoryResponse)
async def add_category(bot_id: str, request: CategoryCreateRequest) -> CategoryResponse:
    """Create a new category."""
    manager = _resolve_agent_manager(bot_id)
    label = request.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Category label cannot be empty")
    try:
        cat = await manager.category_manager.add_category(label)
        return CategoryResponse(key=cat.key, label=cat.label, color=cat.color)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/categories/{category_key}")
async def remove_category(bot_id: str, category_key: str) -> dict[str, str]:
    """Delete a category."""
    manager = _resolve_agent_manager(bot_id)
    success = await manager.category_manager.remove_category(category_key)
    if not success:
        raise HTTPException(status_code=404, detail=f"Category '{category_key}' not found")
    return {"status": "deleted", "key": category_key}


@router.get("/categories/overrides", response_model=dict[str, str])
async def get_category_overrides(bot_id: str) -> dict[str, str]:
    """Get all agent-to-category overrides."""
    manager = _get_agent_manager_optional(bot_id)
    if manager is None:
        return {}
    return manager.category_manager.get_all_overrides()


@router.put("/categories/overrides", response_model=dict[str, str])
async def set_category_override(
    bot_id: str, request: CategoryOverrideRequest
) -> dict[str, str]:
    """Set an agent's display category."""
    manager = _resolve_agent_manager(bot_id)
    await manager.category_manager.set_agent_category(request.agent_id, request.category_key)
    return manager.category_manager.get_all_overrides()


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

def _agent_to_response(agent: AgentConfig) -> AgentResponse:
    """Convert AgentConfig to API response."""
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        model=agent.model,
        temperature=agent.temperature,
        system_prompt=agent.system_prompt,
        skills=agent.skills,
        topics=agent.topics,
        collaborators=agent.collaborators,
        enabled=agent.enabled,
        created_at=agent.created_at.isoformat(),
    )


@router.get("")
async def list_agents(bot_id: str) -> list[AgentResponse]:
    """List all Agents for a bot. Returns empty list if agent system not initialized."""
    agent_manager = _get_agent_manager_optional(bot_id)
    if agent_manager is None:
        return []
    agents = agent_manager.list_agents()
    return [_agent_to_response(a) for a in agents]


@router.post("")
async def create_agent(bot_id: str, request: AgentCreateRequest) -> AgentResponse:
    """Create a new Agent."""
    agent_manager = _resolve_agent_manager(bot_id)

    config = AgentConfig(
        id=request.id or "",
        name=request.name,
        description=request.description,
        model=request.model,
        temperature=request.temperature,
        system_prompt=request.system_prompt,
        skills=request.skills,
        topics=request.topics,
        collaborators=request.collaborators,
        enabled=request.enabled,
    )

    try:
        agent = await agent_manager.create_agent(config)
        if request.display_category:
            await agent_manager.category_manager.set_agent_category(
                agent.id, request.display_category
            )
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{agent_id}")
async def get_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """Get a specific Agent."""
    agent_manager = _resolve_agent_manager(bot_id)
    agent = agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return _agent_to_response(agent)


@router.put("/{agent_id}")
async def update_agent(bot_id: str, agent_id: str, request: AgentUpdateRequest) -> AgentResponse:
    """Update an Agent."""
    agent_manager = _resolve_agent_manager(bot_id)

    update_data = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}
    # remove display_category from the config update; handle it separately
    update_data.pop("display_category", None)

    try:
        agent = await agent_manager.update_agent(agent_id, update_data)
        # Only update category if explicitly provided (not None)
        raw = request.model_dump()
        if "display_category" in raw:
            await agent_manager.category_manager.set_agent_category(
                agent_id, raw["display_category"]
            )
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}")
async def delete_agent(bot_id: str, agent_id: str) -> dict[str, str]:
    """Delete an Agent."""
    agent_manager = _resolve_agent_manager(bot_id)
    success = await agent_manager.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/{agent_id}/enable")
async def enable_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """Enable an Agent."""
    agent_manager = _resolve_agent_manager(bot_id)
    try:
        agent = await agent_manager.enable_agent(agent_id)
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{agent_id}/disable")
async def disable_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """Disable an Agent."""
    agent_manager = _resolve_agent_manager(bot_id)
    try:
        agent = await agent_manager.disable_agent(agent_id)
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{agent_id}/delegate")
async def delegate_task(
    bot_id: str, agent_id: str, request: DelegateTaskRequest
) -> DelegateTaskResponse:
    """Delegate a task to another Agent."""
    agent_manager = _resolve_agent_manager(bot_id)
    try:
        correlation_id, response_msg = await agent_manager.delegate_task(
            from_agent_id=agent_id,
            to_agent_id=request.to_agent_id,
            task=request.task,
            context=request.context,
            wait_response=request.wait_response,
        )
        return DelegateTaskResponse(
            correlation_id=correlation_id,
            response=response_msg.content if response_msg else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{agent_id}/broadcast")
async def broadcast_event(
    bot_id: str, agent_id: str, request: BroadcastEventRequest
) -> dict[str, str]:
    """Broadcast an event to all Agents."""
    agent_manager = _resolve_agent_manager(bot_id)
    await agent_manager.broadcast_event(
        agent_id=agent_id,
        topic=request.topic,
        content=request.content,
        context=request.context,
    )
    return {"status": "broadcasted", "topic": request.topic}


def _empty_system_status() -> dict[str, Any]:
    return {
        "total_agents": 0,
        "enabled_agents": 0,
        "subscribed_agents": [],
        "zmq_initialized": False,
        "agent_id": None,
    }


@router.get("/{agent_id}/status")
async def get_agent_status(bot_id: str, agent_id: str) -> dict[str, Any]:
    """Get Agent status; returns empty status if agent system not initialized."""
    agent_manager = _get_agent_manager_optional(bot_id)

    # Special path: /agents/system-status/status
    if agent_id == "system-status":
        if agent_manager is None:
            return _empty_system_status()
        return agent_manager.get_status()

    if agent_manager is None:
        raise HTTPException(
            status_code=404, detail=f"Agent system not initialized for bot '{bot_id}'"
        )
    agent = agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    status = agent_manager.get_status()
    status["agent_id"] = agent_id
    status["agent_name"] = agent.name
    status["enabled"] = agent.enabled
    status["bot_id"] = bot_id  # shared bus: include bot context
    status["full_agent_id"] = f"{bot_id}:{agent_id}"  # global unique identifier
    return status


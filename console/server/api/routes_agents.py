"""API routes for multi-agent management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from console.server.api.state import get_state_manager
from console.server.extension.agents import AgentConfig, AgentManager

router = APIRouter(prefix="/api/bots/{bot_id}/agents")


def _get_agent_manager_optional(bot_id: str) -> AgentManager | None:
    """获取Bot的AgentManager实例，未初始化时返回None"""
    state_manager = get_state_manager()
    state = state_manager.get_state(bot_id)
    if not hasattr(state, "_agent_manager") or state._agent_manager is None:
        return None
    return state._agent_manager


def _resolve_agent_manager(bot_id: str) -> AgentManager:
    """获取Bot的AgentManager实例，未初始化时抛出404"""
    manager = _get_agent_manager_optional(bot_id)
    if manager is None:
        logger.warning(f"Agent system not initialized for bot '{bot_id}'")
        raise HTTPException(
            status_code=404, detail=f"Agent system not initialized for bot '{bot_id}'"
        )
    return manager


class AgentCreateRequest(BaseModel):
    """创建Agent的请求"""

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


class AgentUpdateRequest(BaseModel):
    """更新Agent的请求"""

    name: str | None = None
    description: str | None = None
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    skills: list[str] | None = None
    topics: list[str] | None = None
    collaborators: list[str] | None = None
    enabled: bool | None = None


class AgentResponse(BaseModel):
    """Agent响应"""

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


def _agent_to_response(agent: AgentConfig) -> AgentResponse:
    """将AgentConfig转换为API响应"""
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
    """获取Bot下所有Agent列表；未初始化 agent 系统时返回空列表"""
    agent_manager = _get_agent_manager_optional(bot_id)
    if agent_manager is None:
        return []
    agents = agent_manager.list_agents()
    return [_agent_to_response(a) for a in agents]


@router.post("")
async def create_agent(bot_id: str, request: AgentCreateRequest) -> AgentResponse:
    """创建新Agent"""
    agent_manager = _resolve_agent_manager(bot_id)

    # 构建AgentConfig
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
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{agent_id}")
async def get_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """获取指定Agent详情"""
    agent_manager = _resolve_agent_manager(bot_id)
    agent = agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return _agent_to_response(agent)


@router.put("/{agent_id}")
async def update_agent(bot_id: str, agent_id: str, request: AgentUpdateRequest) -> AgentResponse:
    """更新Agent配置"""
    agent_manager = _resolve_agent_manager(bot_id)

    # 构建更新字典 (排除None值)
    update_data = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}

    try:
        agent = await agent_manager.update_agent(agent_id, update_data)
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}")
async def delete_agent(bot_id: str, agent_id: str) -> dict[str, str]:
    """删除Agent"""
    agent_manager = _resolve_agent_manager(bot_id)
    success = await agent_manager.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/{agent_id}/enable")
async def enable_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """启用Agent"""
    agent_manager = _resolve_agent_manager(bot_id)
    try:
        agent = await agent_manager.enable_agent(agent_id)
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{agent_id}/disable")
async def disable_agent(bot_id: str, agent_id: str) -> AgentResponse:
    """禁用Agent"""
    agent_manager = _resolve_agent_manager(bot_id)
    try:
        agent = await agent_manager.disable_agent(agent_id)
        return _agent_to_response(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class DelegateTaskRequest(BaseModel):
    """委托任务请求"""

    to_agent_id: str
    task: str
    context: dict[str, Any] = {}
    wait_response: bool = False


class DelegateTaskResponse(BaseModel):
    """委托任务响应"""

    correlation_id: str
    response: str | None


@router.post("/{agent_id}/delegate")
async def delegate_task(
    bot_id: str, agent_id: str, request: DelegateTaskRequest
) -> DelegateTaskResponse:
    """将任务委托给另一个Agent"""
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


class BroadcastEventRequest(BaseModel):
    """广播事件请求"""

    topic: str
    content: str
    context: dict[str, Any] = {}


@router.post("/{agent_id}/broadcast")
async def broadcast_event(
    bot_id: str, agent_id: str, request: BroadcastEventRequest
) -> dict[str, str]:
    """广播事件给所有Agent"""
    agent_manager = _resolve_agent_manager(bot_id)
    await agent_manager.broadcast_event(
        agent_id=agent_id,
        topic=request.topic,
        content=request.content,
        context=request.context,
    )
    return {"status": "broadcasted", "topic": request.topic}


def _empty_system_status() -> dict[str, Any]:
    """Agent 系统未初始化时的默认状态"""
    return {
        "total_agents": 0,
        "enabled_agents": 0,
        "subscribed_agents": [],
        "zmq_initialized": False,
        "agent_id": None,
    }


@router.get("/{agent_id}/status")
async def get_agent_status(bot_id: str, agent_id: str) -> dict[str, Any]:
    """获取Agent状态；未初始化 agent 系统时返回空状态"""
    agent_manager = _get_agent_manager_optional(bot_id)

    # 特殊处理系统状态请求
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

    # 验证Agent身份
    agent_manager.zmq_bus.set_agent_id(agent_id)

    status = agent_manager.get_status()
    status["agent_id"] = agent_id
    status["agent_name"] = agent.name
    status["enabled"] = agent.enabled
    return status

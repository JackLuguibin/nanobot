"""
facade/agent/manager.py - AgentFacade

Agent 的统一管理接口。
设计原则：
- 仅读取 nanobot AgentLoop 状态，不直接修改运行时
- 配置变更通过 ConfigBridge 写入配置文件
- 多 Agent 支持（通过 AgentManager extension）
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class AgentFacade(BaseManager[dict[str, Any]]):
    """
    Agent 统一管理门面。

    职责：
    - 持有 AgentLoop 和 AgentManager 引用
    - 提供 Agent 列表、健康检查、配置读取
    - 配置变更通过 ConfigBridge 写入

    设计原则：
    - 仅通过配置驱动与 nanobot 交互
    - 不直接调用 AgentLoop 的运行时修改方法
    """

    def __init__(
        self,
        bot_id: str,
        agent_loop: Any = None,
        agent_manager: Any = None,
    ) -> None:
        super().__init__(bot_id)
        self._agent_loop = agent_loop
        self._agent_manager = agent_manager

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有 Agent（主 Agent + 子 Agent）。"""
        agents = []

        # 主 Agent（AgentLoop）
        if self._agent_loop:
            agents.append({
                "id": "main",
                "name": "Main Agent",
                "type": "main",
                "model": getattr(self._agent_loop, "model", None),
                "provider": getattr(self._agent_loop, "_provider", None).__class__.__name__
                if hasattr(self._agent_loop, "_provider") else None,
                "running": True,
                "session_count": self._get_active_session_count(),
            })

        # 子 Agent（通过 AgentManager）
        if self._agent_manager and hasattr(self._agent_manager, "list_agents"):
            try:
                for agent_id, agent_cfg in self._agent_manager.list_agents():
                    agents.append({
                        "id": agent_id,
                        "name": agent_cfg.get("name", agent_id),
                        "type": agent_cfg.get("type", "subagent"),
                        "model": agent_cfg.get("model"),
                        "provider": agent_cfg.get("provider"),
                        "running": True,
                        "session_count": 0,
                    })
            except Exception as e:
                logger.debug("Failed to list sub-agents: {}", e)

        return agents

    def get(self, identifier: str) -> dict[str, Any] | None:
        """根据标识符获取 Agent 详情。"""
        if identifier == "main":
            if not self._agent_loop:
                return None
            return {
                "id": "main",
                "name": "Main Agent",
                "type": "main",
                "model": getattr(self._agent_loop, "model", None),
                "provider": getattr(self._agent_loop, "_provider", None).__class__.__name__
                if hasattr(self._agent_loop, "_provider") else None,
                "running": True,
                "uptime_seconds": getattr(self._agent_loop, "_start_time", 0)
                and (time.time() - self._agent_loop._start_time)
                or 0,
                "session_count": self._get_active_session_count(),
                "message_count": getattr(self._agent_loop, "_message_count", 0),
            }

        # 子 Agent
        if self._agent_manager and hasattr(self._agent_manager, "get_agent"):
            return self._agent_manager.get_agent(identifier)

        return None

    # -------------------------------------------------------------------------
    # 写操作（配置驱动）
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建子 Agent（通过 AgentManager）。"""
        if not self._agent_manager:
            return OperationResult.error("AgentManager not available")
        if not hasattr(self._agent_manager, "create_agent"):
            return OperationResult.error("AgentManager does not support create_agent")

        try:
            agent_id = await self._agent_manager.create_agent(data)
            self.notify(FacadeEvent(
                type=FacadeEventType.CREATED,
                resource_type="agent",
                resource_id=agent_id,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Agent '{agent_id}' created", {"agent_id": agent_id})
        except Exception as e:
            logger.error("Failed to create agent: {}", e)
            return OperationResult.error(f"Failed to create agent: {e}")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新 Agent 配置（通过 ConfigBridge）。"""
        # Agent 配置变更通过配置文件
        try:
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="agent",
                resource_id=identifier,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Agent '{identifier}' updated", {"agent_id": identifier})
        except Exception as e:
            return OperationResult.error(f"Failed to update agent: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """删除子 Agent。"""
        if not self._agent_manager:
            return OperationResult.error("AgentManager not available")
        if not hasattr(self._agent_manager, "delete_agent"):
            return OperationResult.error("AgentManager does not support delete_agent")
        if identifier == "main":
            return OperationResult.error("Cannot delete main agent")

        try:
            await self._agent_manager.delete_agent(identifier)
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="agent",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Agent '{identifier}' deleted", {"agent_id": identifier})
        except Exception as e:
            logger.error("Failed to delete agent '{}': {}", identifier, e)
            return OperationResult.error(f"Failed to delete agent: {e}")

    async def start(self, identifier: str) -> OperationResult:
        """启动 Agent（通过 AgentManager）。"""
        if not self._agent_manager:
            return OperationResult.error("AgentManager not available")
        if not hasattr(self._agent_manager, "start_agent"):
            return OperationResult.error("AgentManager does not support start_agent")

        try:
            await self._agent_manager.start_agent(identifier)
            self.notify(FacadeEvent(
                type=FacadeEventType.STARTED,
                resource_type="agent",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Agent '{identifier}' started")
        except Exception as e:
            return OperationResult.error(f"Failed to start agent: {e}")

    async def stop(self, identifier: str) -> OperationResult:
        """停止 Agent。"""
        if identifier == "main":
            if self._agent_loop and hasattr(self._agent_loop, "_running"):
                self._agent_loop._running = False
                return OperationResult.ok("Main agent stopped")
            return OperationResult.error("Main agent not available")

        if not self._agent_manager or not hasattr(self._agent_manager, "stop_agent"):
            return OperationResult.error("AgentManager does not support stop_agent")

        try:
            await self._agent_manager.stop_agent(identifier)
            self.notify(FacadeEvent(
                type=FacadeEventType.STOPPED,
                resource_type="agent",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Agent '{identifier}' stopped")
        except Exception as e:
            return OperationResult.error(f"Failed to stop agent: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 Agent 组件健康状态。"""
        if not self._agent_loop:
            return HealthCheckResult.unhealthy("AgentLoop not initialized")

        details: dict[str, Any] = {
            "model": getattr(self._agent_loop, "model", None),
            "provider_type": (
                self._agent_loop._provider.__class__.__name__
                if hasattr(self._agent_loop, "_provider") and self._agent_loop._provider
                else None
            ),
            "session_count": self._get_active_session_count(),
        }

        mcp_ok = True
        if hasattr(self._agent_loop, "_mcp_connected"):
            mcp_ok = self._agent_loop._mcp_connected
        details["mcp_connected"] = mcp_ok

        if not mcp_ok:
            return HealthCheckResult.degraded(
                "Agent running but MCP disconnected", details=details
            )

        return HealthCheckResult.healthy("Agent running", details=details)

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _get_active_session_count(self) -> int:
        """获取活跃会话数。"""
        sm = getattr(self._agent_loop, "sessions", None) if self._agent_loop else None
        if sm and hasattr(sm, "_cache"):
            return len(sm._cache)
        return 0

    def get_routing_rules(self) -> list[dict[str, Any]]:
        """获取当前路由规则。"""
        if self._agent_manager and hasattr(self._agent_manager, "get_routing_rules"):
            return self._agent_manager.get_routing_rules()
        return []

    def set_routing_rules(self, rules: list[dict[str, Any]]) -> OperationResult:
        """设置路由规则。"""
        if not self._agent_manager:
            return OperationResult.error("AgentManager not available")
        if not hasattr(self._agent_manager, "set_routing_rules"):
            return OperationResult.error("AgentManager does not support routing rules")

        try:
            self._agent_manager.set_routing_rules(rules)
            return OperationResult.ok("Routing rules updated", {"rules": rules})
        except Exception as e:
            return OperationResult.error(f"Failed to set routing rules: {e}")

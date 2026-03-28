"""
facade/state/manager.py - StateFacade

统一状态管理器，协调所有 Facade Manager。
设计原则：
- 持有所有 Facade Manager 引用
- 提供统一状态聚合和跨 Manager 操作
- 适配 API 层调用
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult
from console.server.facade.state.watcher import StateWatcher


class UnifiedStatus:
    """统一状态数据。"""

    def __init__(
        self,
        bot_id: str,
        agent_status: dict[str, Any] | None = None,
        channel_status: dict[str, Any] | None = None,
        session_status: dict[str, Any] | None = None,
        cron_status: dict[str, Any] | None = None,
        gateway_status: dict[str, Any] | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.agent_status = agent_status or {}
        self.channel_status = channel_status or {}
        self.session_status = session_status or {}
        self.cron_status = cron_status or {}
        self.gateway_status = gateway_status or {}
        self.timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "agent": self.agent_status,
            "channel": self.channel_status,
            "session": self.session_status,
            "cron": self.cron_status,
            "gateway": self.gateway_status,
            "timestamp": self.timestamp,
        }


class StateFacade:
    """
    统一状态管理器。

    职责：
    - 持有所有 Facade Manager 引用
    - 提供 get_unified_status() 并行收集状态
    - 提供 execute_operation() 跨 Manager 操作
    - 管理 StateWatcher 广播

    设计原则：
    - 不直接操作 nanobot，通过各 Manager 代理
    - 状态收集并行执行，提升性能
    """

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self._agent_facade: Any = None
        self._channel_facade: Any = None
        self._session_facade: Any = None
        self._cron_facade: Any = None
        self._gateway_bridge: Any = None
        # 扩展 Manager（通过扩展属性关联）
        self._alert_facade: Any = None
        self._status_facade: Any = None
        self._tools_facade: Any = None
        self._workspace_facade: Any = None
        self._plans_facade: Any = None
        self._usage_facade: Any = None
        self._env_facade: Any = None
        self._mcp_facade: Any = None
        self._memory_facade: Any = None
        self._watcher = StateWatcher()
        self._lock = asyncio.Lock()

    def set_agent_facade(self, facade: Any) -> None:
        self._agent_facade = facade
        if facade:
            facade.subscribe(self._watcher.on_facade_event)

    def set_channel_facade(self, facade: Any) -> None:
        self._channel_facade = facade
        if facade:
            facade.subscribe(self._watcher.on_facade_event)

    def set_session_facade(self, facade: Any) -> None:
        self._session_facade = facade
        if facade:
            facade.subscribe(self._watcher.on_facade_event)

    def set_cron_facade(self, facade: Any) -> None:
        self._cron_facade = facade
        if facade:
            facade.subscribe(self._watcher.on_facade_event)

    def set_gateway_bridge(self, bridge: Any) -> None:
        self._gateway_bridge = bridge
        if bridge and hasattr(bridge, "subscribe_status"):
            bridge.subscribe_status(self._watcher.on_facade_event)

    def subscribe(self, callback: Any) -> None:
        """注册统一状态监听器。"""
        self._watcher.subscribe(callback)

    def unsubscribe(self, callback: Any) -> None:
        """取消统一状态监听器。"""
        self._watcher.unsubscribe(callback)

    async def get_unified_status(self) -> dict[str, Any]:
        """
        并行收集所有组件状态，返回统一状态。
        """
        status = UnifiedStatus(bot_id=self.bot_id)
        tasks = []

        if self._agent_facade:
            tasks.append(self._collect_agent())
        if self._channel_facade:
            tasks.append(self._collect_channel())
        if self._session_facade:
            tasks.append(self._collect_session())
        if self._cron_facade:
            tasks.append(self._collect_cron())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.debug("Status collection error: {}", r)
            elif isinstance(r, tuple):
                field, data = r
                setattr(status, field, data)

        status.timestamp = datetime.now().isoformat()
        return status.to_dict()

    async def _collect_agent(self) -> tuple[str, dict[str, Any]]:
        if not self._agent_facade:
            return "agent_status", {}
        try:
            health = self._agent_facade.health_check()
            return "agent_status", health.to_dict()
        except Exception as e:
            logger.debug("Agent status error: {}", e)
            return "agent_status", {}

    async def _collect_channel(self) -> tuple[str, dict[str, Any]]:
        if not self._channel_facade:
            return "channel_status", {}
        try:
            health = self._channel_facade.health_check()
            return "channel_status", health.to_dict()
        except Exception as e:
            logger.debug("Channel status error: {}", e)
            return "channel_status", {}

    async def _collect_session(self) -> tuple[str, dict[str, Any]]:
        if not self._session_facade:
            return "session_status", {}
        try:
            health = self._session_facade.health_check()
            return "session_status", health.to_dict()
        except Exception as e:
            logger.debug("Session status error: {}", e)
            return "session_status", {}

    async def _collect_cron(self) -> tuple[str, dict[str, Any]]:
        if not self._cron_facade:
            return "cron_status", {}
        try:
            health = self._cron_facade.health_check()
            return "cron_status", health.to_dict()
        except Exception as e:
            logger.debug("Cron status error: {}", e)
            return "cron_status", {}

    async def execute_operation(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
        data: dict[str, Any] | None = None,
    ) -> OperationResult:
        """
        执行跨 Manager 的操作。
        operation: create/update/delete/start/stop
        resource_type: agent/channel/session/cron/provider/skill
        """
        async with self._lock:
            facade = self._get_facade(resource_type)
            if not facade:
                return OperationResult.error(f"Unknown resource type: {resource_type}")

            if not hasattr(facade, operation):
                return OperationResult.error(f"Operation '{operation}' not found on {resource_type}")

            try:
                method = getattr(facade, operation)
                if asyncio.iscoroutinefunction(method):
                    return await method(resource_id, data or {})
                else:
                    return method(resource_id, data or {})
            except Exception as e:
                logger.error("execute_operation failed: {} {} {}: {}", operation, resource_type, resource_id, e)
                return OperationResult.error(f"Operation failed: {e}")

    def _get_facade(self, resource_type: str) -> Any:
        mapping = {
            "agent": self._agent_facade,
            "channel": self._channel_facade,
            "session": self._session_facade,
            "cron": self._cron_facade,
            "alert": self._alert_facade,
            "status": self._status_facade,
            "tools": self._tools_facade,
            "workspace": self._workspace_facade,
            "plans": self._plans_facade,
            "usage": self._usage_facade,
            "env": self._env_facade,
            "mcp": self._mcp_facade,
            "memory": self._memory_facade,
        }
        return mapping.get(resource_type)

    def get_gateway_status(self) -> dict[str, Any]:
        """获取 Gateway 状态。"""
        if not self._gateway_bridge:
            return {}
        try:
            return self._gateway_bridge.get_status().to_dict()
        except Exception:
            return {}

"""
facade/status/manager.py - StatusFacade

统一状态收集接口。
设计原则：
- 并行收集所有组件状态
- 不直接操作 nanobot，仅读取
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class StatusFacade(BaseManager[dict[str, Any]]):
    """
    统一状态收集门面。

    职责：
    - 并行收集 Agent、Channel、Session、Cron、MCP 等组件状态
    - 提供统一的 get_status() 方法
    - 不修改 nanobot 状态

    设计原则：
    - 仅读取状态
    - 收集各 Facade Manager 的健康检查结果
    """

    def __init__(
        self,
        bot_id: str,
        agent_loop: Any = None,
        channel_manager: Any = None,
        session_manager: Any = None,
        cron_service: Any = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(bot_id)
        self._agent_loop = agent_loop
        self._channel_manager = channel_manager
        self._session_manager = session_manager
        self._cron_service = cron_service
        self._config = config or {}

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有组件状态摘要。"""
        return [self._collect_sync()]

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取状态详情（identifier 被忽略，始终返回统一状态）。"""
        return self._collect_sync()

    # -------------------------------------------------------------------------
    # 写操作（不支持）
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Status is read-only")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Status is read-only")

    async def delete(self, identifier: str) -> OperationResult:
        return OperationResult.error("Status is read-only")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """收集整体健康状态。"""
        checks: dict[str, bool] = {}

        if self._agent_loop:
            checks["agent"] = True
        if self._channel_manager:
            checks["channel"] = True
        if self._session_manager:
            checks["session"] = True
        if self._cron_service:
            checks["cron"] = True

        all_healthy = all(checks.values())
        details = {"checks": checks, "bot_id": self.bot_id}

        if not checks:
            return HealthCheckResult.unknown("No components available", details=details)
        if all_healthy:
            return HealthCheckResult.healthy(f"All {len(checks)} components healthy", details=details)
        return HealthCheckResult.degraded(f"Some components unhealthy", details=details)

    # -------------------------------------------------------------------------
    # 核心：收集状态
    # -------------------------------------------------------------------------

    def _collect_sync(self) -> dict[str, Any]:
        """同步收集所有组件状态。"""
        self._reset_daily_stats()

        # Channels
        channels = self._collect_channels()

        # MCP servers
        mcp_servers = self._collect_mcp()

        # Active sessions
        active_sessions = self._count_active_sessions()

        # Model
        model = None
        if self._agent_loop and hasattr(self._agent_loop, "model"):
            model = self._agent_loop.model

        # Token usage
        token_usage = self._get_usage_today()

        return {
            "running": self._agent_loop is not None,
            "uptime_seconds": self._get_uptime_seconds(),
            "model": model,
            "active_sessions": active_sessions,
            "messages_today": self._messages_today,
            "token_usage": token_usage,
            "channels": channels,
            "mcp_servers": mcp_servers,
            "bot_id": self.bot_id,
        }

    async def get_status(self) -> dict[str, Any]:
        """异步收集所有组件状态（供 API 层调用）。"""
        return self._collect_sync()

    # -------------------------------------------------------------------------
    # 子收集器
    # -------------------------------------------------------------------------

    def _collect_channels(self) -> list[dict[str, Any]]:
        """收集通道状态。"""
        channels = []
        ch_dict = getattr(self._channel_manager, "channels", None) or getattr(
            self._channel_manager, "_channels", None
        )
        if self._channel_manager and ch_dict is not None:
            for name, channel in ch_dict.items():
                channels.append({
                    "name": name,
                    "enabled": True,
                    "status": "online" if hasattr(channel, "_connected") and channel._connected else "offline",
                    "stats": {},
                })
        return channels

    def _collect_mcp(self) -> list[dict[str, Any]]:
        """收集 MCP 服务器状态。"""
        mcp_servers = []
        if self._agent_loop and hasattr(self._agent_loop, "_mcp_servers"):
            for name, config in self._agent_loop._mcp_servers.items():
                mcp_servers.append({
                    "name": name,
                    "status": "connected" if getattr(self._agent_loop, "_mcp_connected", False) else "disconnected",
                    "server_type": "stdio" if "command" in config else "http",
                    "last_connected": None,
                    "error": None,
                })
        return mcp_servers

    def _count_active_sessions(self) -> int:
        """统计活跃会话数。"""
        if self._session_manager and hasattr(self._session_manager, "_cache"):
            return len(self._session_manager._cache)
        return 0

    def _get_uptime_seconds(self) -> float:
        """获取运行时间。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_start_time"):
            return 0.0
        start = getattr(self._agent_loop, "_start_time", None)
        if start is None:
            return 0.0
        import time
        return time.time() - start

    def _get_usage_today(self) -> dict[str, Any]:
        """获取今日 token 使用量。"""
        try:
            from console.server.extension.usage import get_usage_today
            return get_usage_today(self.bot_id)
        except Exception:
            return {}

    # -------------------------------------------------------------------------
    # 每日统计
    # -------------------------------------------------------------------------

    def _reset_daily_stats(self) -> None:
        """每日重置消息计数。"""
        from datetime import date
        today = date.today().isoformat()
        if getattr(self, "_last_reset_date", "") != today:
            self._messages_today = 0
            self._last_reset_date = today

    def increment_messages(self) -> int:
        """递增今日消息计数。"""
        self._reset_daily_stats()
        self._messages_today += 1
        return self._messages_today

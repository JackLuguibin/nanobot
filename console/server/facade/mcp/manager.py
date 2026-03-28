"""
facade/mcp/manager.py - MCPFacade

MCP 服务器管理接口。
设计原则：
- 持有 agent_loop，通过 nanobot AgentLoop 操作 MCP
- 提供测试、刷新操作
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class MCPFacade(BaseManager[dict[str, Any]]):
    """
    MCP 服务器管理门面。

    职责：
    - 持有 AgentLoop 引用
    - 提供 MCP 服务器列表、测试、刷新
    - 不修改 nanobot 配置（MCP 配置在 ConfigBridge）

    设计原则：
    - 运行时操作（MCP 连接测试/刷新）通过 AgentLoop
    - 配置变更通过 ConfigBridge
    """

    def __init__(self, bot_id: str, agent_loop: Any = None) -> None:
        super().__init__(bot_id)
        self._agent_loop = agent_loop

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有 MCP 服务器状态。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_mcp_servers"):
            return []

        servers = self._agent_loop._mcp_servers or {}
        result = []
        for name, config in servers.items():
            result.append({
                "name": name,
                "status": "connected" if getattr(self._agent_loop, "_mcp_connected", False) else "disconnected",
                "server_type": "stdio" if "command" in config else "http",
                "last_connected": None,
                "error": None,
            })
        return result

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定 MCP 服务器详情。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_mcp_servers"):
            return None

        servers = self._agent_loop._mcp_servers or {}
        if identifier not in servers:
            return None

        config = servers[identifier]
        return {
            "name": identifier,
            "status": "connected" if getattr(self._agent_loop, "_mcp_connected", False) else "disconnected",
            "server_type": "stdio" if "command" in config else "http",
            "config": config,
        }

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("MCP servers must be configured in config file")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("MCP config must be updated via ConfigBridge")

    async def delete(self, identifier: str) -> OperationResult:
        return OperationResult.error("MCP servers must be removed from config file")

    # -------------------------------------------------------------------------
    # MCP 运行时操作
    # -------------------------------------------------------------------------

    async def test(self, name: str) -> dict[str, Any]:
        """测试 MCP 连接。返回延迟和成功状态。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_mcp_servers"):
            return {"name": name, "success": False, "message": "AgentLoop or MCP not available"}

        servers = self._agent_loop._mcp_servers or {}
        if name not in servers:
            return {"name": name, "success": False, "message": f"MCP server '{name}' not found"}

        start = time.monotonic()
        try:
            if getattr(self._agent_loop, "_mcp_connected", False):
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return {"name": name, "success": True, "latency_ms": elapsed_ms}
            return {"name": name, "success": False, "message": "MCP not connected"}
        except Exception as e:
            return {"name": name, "success": False, "message": str(e)}

    async def refresh(self, name: str) -> dict[str, Any]:
        """重新连接 MCP 服务器。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_mcp_servers"):
            return {"name": name, "success": False, "message": "AgentLoop or MCP not available"}

        servers = self._agent_loop._mcp_servers or {}
        if name not in servers:
            return {"name": name, "success": False, "message": f"MCP server '{name}' not found"}

        try:
            if hasattr(self._agent_loop, "close_mcp"):
                await self._agent_loop.close_mcp()
            if hasattr(self._agent_loop, "_connect_mcp"):
                self._agent_loop._mcp_connected = False
                await self._agent_loop._connect_mcp()
            return {"name": name, "success": True}
        except Exception as e:
            return {"name": name, "success": False, "message": str(e)}

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 MCP 连接状态。"""
        if not self._agent_loop or not hasattr(self._agent_loop, "_mcp_servers"):
            return HealthCheckResult.unknown("MCP not configured")

        servers = self._agent_loop._mcp_servers or {}
        if not servers:
            return HealthCheckResult.unknown("No MCP servers configured")

        connected = getattr(self._agent_loop, "_mcp_connected", False)
        details = {
            "servers": list(servers.keys()),
            "connected": connected,
            "count": len(servers),
        }

        if connected:
            return HealthCheckResult.healthy(f"{len(servers)} MCP servers, connected", details=details)
        return HealthCheckResult.degraded(f"{len(servers)} MCP servers, disconnected", details=details)

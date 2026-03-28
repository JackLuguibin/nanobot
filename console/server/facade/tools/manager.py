"""
facade/tools/manager.py - ToolsFacade

工具调用日志接口。
设计原则：
- 持有 bot_id，读取工具日志
- 不修改 nanobot
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class ToolsFacade(BaseManager[dict[str, Any]]):
    """
    工具调用日志门面。

    职责：
    - 获取工具调用日志（内存 + 持久化 activity）

    设计原则：
    - 仅读取
    - 通过 api/state.py 读取 BotState 的 tool_call_logs
    - 通过 extension/activity.py 读取持久化日志
    """

    def __init__(self, bot_id: str, tool_call_logs: list[dict] | None = None) -> None:
        super().__init__(bot_id)
        self._tool_call_logs = tool_call_logs or []

    def set_logs(self, logs: list[dict]) -> None:
        """设置工具日志列表（由 FacadeManager 注入）。"""
        self._tool_call_logs = logs

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """获取工具日志列表。"""
        return self._collect_logs(limit=50)

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定工具调用详情。identifier = 日志 id。"""
        logs = self._collect_logs(limit=1000)
        return next((log for log in logs if log.get("id") == identifier), None)

    # -------------------------------------------------------------------------
    # 写操作（不支持）
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Tool logs are generated automatically")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Tool logs are read-only")

    async def delete(self, identifier: str) -> OperationResult:
        return OperationResult.error("Tool logs are read-only")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """工具日志是纯数据层。"""
        return HealthCheckResult.healthy(
            "Tools facade available",
            details={"bot_id": self.bot_id, "in_memory_logs": len(self._tool_call_logs)}
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _collect_logs(self, limit: int = 50, tool_name: str | None = None) -> list[dict[str, Any]]:
        """收集工具调用日志（内存 + activity）。"""
        logs = list(self._tool_call_logs)

        if self.bot_id != "_empty":
            try:
                from console.server.extension.activity import get_activity
                activity = get_activity(self.bot_id, limit=limit * 2, activity_type="tool_call")
                seen_ids = {log.get("id") for log in logs}
                for entry in activity:
                    if entry.get("id") in seen_ids:
                        continue
                    log = self._activity_to_tool_log(entry)
                    if tool_name and log.get("tool_name") != tool_name:
                        continue
                    logs.append(log)
                    seen_ids.add(entry.get("id"))
            except Exception as e:
                logger.debug("Failed to collect activity tool logs: {}", e)

        if tool_name:
            logs = [log for log in logs if log.get("tool_name") == tool_name]

        logs = sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        return logs

    @staticmethod
    def _activity_to_tool_log(entry: dict[str, Any]) -> dict[str, Any]:
        """转换 activity 条目为工具日志格式。"""
        data = entry.get("data") or {}
        ts = entry.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            ts_str = datetime.fromtimestamp(ts).isoformat()
        else:
            ts_str = str(ts)
        return {
            "id": entry.get("id", ""),
            "tool_name": data.get("tool_name", ""),
            "arguments": data.get("arguments") or {},
            "result": data.get("result") or data.get("error"),
            "status": "success" if data.get("status") == "success" else "error",
            "duration_ms": data.get("duration_ms", 0),
            "timestamp": ts_str,
        }

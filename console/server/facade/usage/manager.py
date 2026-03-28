"""
facade/usage/manager.py - UsageFacade

Token 使用量追踪接口。
设计原则：
- 持有 bot_id，通过 extension/usage.py 操作
- 提供使用量历史、成本查询
- 不修改 nanobot，仅读取
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class UsageFacade(BaseManager[dict[str, Any]]):
    """
    Token 使用量追踪门面。

    职责：
    - 获取今日/历史 token 使用量
    - 获取成本统计
    - 查询使用量历史（图表数据）

    设计原则：
    - 仅读取使用量数据
    - 通过 extension/usage 操作
    """

    def __init__(self, bot_id: str) -> None:
        super().__init__(bot_id)

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """获取使用量历史（最近 14 天）。"""
        try:
            from console.server.extension.usage import get_usage_history as _get
            return _get(self.bot_id, days=14)
        except Exception as e:
            logger.debug("Failed to get usage history for bot '{}': {}", self.bot_id, e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定日期的使用量。identifier = ISO date string"""
        try:
            from console.server.extension.usage import get_usage_cost as _get
            target = date.fromisoformat(identifier) if identifier else None
            return _get(self.bot_id, target)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 写操作（不支持）
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Usage data is generated automatically")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Usage data is read-only")

    async def delete(self, identifier: str) -> OperationResult:
        return OperationResult.error("Usage data is read-only")

    # -------------------------------------------------------------------------
    # 查询接口
    # -------------------------------------------------------------------------

    async def get_today(self) -> dict[str, Any]:
        """获取今日使用量。"""
        try:
            from console.server.extension.usage import get_usage_today as _get
            return _get(self.bot_id)
        except Exception as e:
            logger.debug("Failed to get today's usage for bot '{}': {}", self.bot_id, e)
            return {}

    async def get_cost(self, date_str: str | None = None) -> dict[str, Any]:
        """获取指定日期成本。"""
        try:
            from console.server.extension.usage import get_usage_cost as _get
            target = date.fromisoformat(date_str) if date_str else None
            return _get(self.bot_id, target)
        except Exception as e:
            logger.debug("Failed to get usage cost for bot '{}': {}", self.bot_id, e)
            return {"error": str(e)}

    async def get_history(self, days: int = 14) -> list[dict[str, Any]]:
        """获取使用量历史（图表数据）。"""
        try:
            from console.server.extension.usage import get_usage_history as _get
            return _get(self.bot_id, days=min(max(days, 1), 90))
        except Exception as e:
            logger.debug("Failed to get usage history for bot '{}': {}", self.bot_id, e)
            return []

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """使用量追踪是纯数据层，总是健康。"""
        return HealthCheckResult.healthy(
            "Usage facade available",
            details={"bot_id": self.bot_id}
        )

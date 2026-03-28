"""
facade/alert/manager.py - AlertFacade

告警管理接口。
设计原则：
- 持有 bot_id，通过 extension/alerts.py 和 extension/health.py 操作
- 提供告警列表、刷新、关闭
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class AlertFacade(BaseManager[dict[str, Any]]):
    """
    告警管理门面。

    职责：
    - 获取告警列表
    - 刷新告警（基于健康检查）
    - 关闭告警

    设计原则：
    - 仅通过 extension/alerts 与持久化交互
    - 不直接操作 nanobot
    """

    def __init__(
        self,
        bot_id: str,
        agent_loop: Any = None,
        cron_service: Any = None,
    ) -> None:
        super().__init__(bot_id)
        self._agent_loop = agent_loop
        self._cron_service = cron_service

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """获取告警列表。"""
        try:
            from console.server.extension.alerts import get_alerts as _get
            return _get(self.bot_id, include_dismissed=False)
        except Exception as e:
            logger.debug("Failed to get alerts for bot '{}': {}", self.bot_id, e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定告警详情。"""
        try:
            from console.server.extension.alerts import get_alerts as _get
            alerts = _get(self.bot_id, include_dismissed=True)
            return next((a for a in alerts if a.get("id") == identifier), None)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新告警状态。"""
        if data.get("dismissed"):
            return await self.delete(identifier)
        return OperationResult.ok("Alert updated")

    async def delete(self, identifier: str) -> OperationResult:
        """关闭告警。"""
        try:
            from console.server.extension.alerts import dismiss_alert as _dismiss
            ok = _dismiss(self.bot_id, identifier)
            if not ok:
                return OperationResult.error(f"Alert '{identifier}' not found")
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="alert",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Alert '{identifier}' dismissed")
        except Exception as e:
            return OperationResult.error(f"Failed to dismiss alert: {e}")

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Alerts are generated automatically by health checks")

    # -------------------------------------------------------------------------
    # 刷新告警
    # -------------------------------------------------------------------------

    async def refresh(self) -> OperationResult:
        """重新运行健康检查，刷新告警列表。"""
        try:
            from console.server.extension.alerts import refresh_alerts
            from console.server.extension.usage import get_usage_today

            status = {}
            if self._agent_loop:
                status = await self._get_agent_status()

            usage_today = get_usage_today(self.bot_id)
            cron_jobs: list[dict[str, Any]] = []
            if self._cron_service:
                try:
                    jobs = self._cron_service.list_jobs(include_disabled=True)
                    for j in jobs:
                        cron_jobs.append({
                            "id": j.id,
                            "name": j.name,
                            "enabled": j.enabled,
                            "state": {
                                "next_run_at_ms": j.state.next_run_at_ms,
                                "last_run_at_ms": j.state.last_run_at_ms,
                            },
                        })
                except Exception as e:
                    logger.debug("Failed to serialize cron job '{}': {}", j.id, e)

            refresh_alerts(self.bot_id, status, cron_jobs, usage_today)
            return OperationResult.ok("Alerts refreshed")
        except Exception as e:
            return OperationResult.error(f"Failed to refresh alerts: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查告警系统状态。"""
        try:
            from console.server.extension.alerts import get_alerts as _get
            alerts = _get(self.bot_id, include_dismissed=False)
            active = len(alerts)
            details = {"active_alerts": active}
            if active == 0:
                return HealthCheckResult.healthy("No active alerts", details=details)
            return HealthCheckResult.degraded(f"{active} active alerts", details=details)
        except Exception as e:
            return HealthCheckResult.unknown(f"Alert system unavailable: {e}")

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    async def _get_agent_status(self) -> dict[str, Any]:
        """获取 Agent 状态（用于告警刷新）。"""
        status = {}
        if self._agent_loop and hasattr(self._agent_loop, "model"):
            status["model"] = self._agent_loop.model
        if self._agent_loop and hasattr(self._agent_loop, "_mcp_connected"):
            status["mcp_connected"] = self._agent_loop._mcp_connected
        return status

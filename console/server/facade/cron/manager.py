"""
facade/cron/manager.py - CronFacade

Cron 任务的统一管理接口。
设计原则：
- 直接操作 nanobot CronService（有限修改权限）
- 持久化通过 CronService 自身机制（JSON 文件）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class CronFacade(BaseManager[dict[str, Any]]):
    """
    Cron 统一管理门面。

    职责：
    - 持有 CronService 引用
    - 提供 Cron 任务 CRUD、手动触发
    - 集成 cron_history extension

    设计原则：
    - 直接操作 CronService（有限修改权限）
    - 持久化通过 CronService 自身机制
    """

    def __init__(self, bot_id: str, cron_service: Any = None) -> None:
        super().__init__(bot_id)
        self._cron_service = cron_service

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有 Cron 任务。"""
        if not self._cron_service:
            return []

        jobs = self._cron_service.list_jobs(include_disabled=True)
        result = []
        for job in jobs:
            result.append({
                "id": job.id,
                "name": job.name,
                "enabled": job.enabled,
                "schedule": {
                    "kind": job.schedule.kind,
                    "at_ms": job.schedule.at_ms,
                    "every_ms": job.schedule.every_ms,
                    "expr": job.schedule.expr,
                    "tz": job.schedule.tz,
                },
                "payload": {
                    "kind": job.payload.kind,
                    "message": job.payload.message,
                    "deliver": job.payload.deliver,
                    "channel": job.payload.channel,
                    "to": job.payload.to,
                },
                "state": {
                    "next_run_at_ms": job.state.next_run_at_ms,
                    "last_run_at_ms": job.state.last_run_at_ms,
                    "last_status": job.state.last_status,
                    "last_error": job.state.last_error,
                    "run_history": [
                        {
                            "run_at_ms": r.run_at_ms,
                            "status": r.status,
                            "duration_ms": r.duration_ms,
                            "error": r.error,
                        }
                        for r in job.state.run_history
                    ],
                },
                "created_at_ms": job.created_at_ms,
                "updated_at_ms": job.updated_at_ms,
            })
        return result

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定 Cron 任务详情。"""
        if not self._cron_service:
            return None

        job = self._cron_service.get_job(identifier)
        if not job:
            return None

        return {
            "id": job.id,
            "name": job.name,
            "enabled": job.enabled,
            "schedule": {
                "kind": job.schedule.kind,
                "at_ms": job.schedule.at_ms,
                "every_ms": job.schedule.every_ms,
                "expr": job.schedule.expr,
                "tz": job.schedule.tz,
            },
            "payload": {
                "kind": job.payload.kind,
                "message": job.payload.message,
                "deliver": job.payload.deliver,
                "channel": job.payload.channel,
                "to": job.payload.to,
            },
            "state": {
                "next_run_at_ms": job.state.next_run_at_ms,
                "last_run_at_ms": job.state.last_run_at_ms,
                "last_status": job.state.last_status,
                "last_error": job.state.last_error,
                "run_history": [
                    {
                        "run_at_ms": r.run_at_ms,
                        "status": r.status,
                        "duration_ms": r.duration_ms,
                        "error": r.error,
                    }
                    for r in job.state.run_history
                ],
            },
            "created_at_ms": job.created_at_ms,
            "updated_at_ms": job.updated_at_ms,
        }

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建新 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        name = data.get("name")
        schedule_data = data.get("schedule", {})
        message = data.get("message", "")

        if not name:
            return OperationResult.error("Job name is required")

        try:
            from nanobot.cron.types import CronSchedule
            schedule = CronSchedule(
                kind=schedule_data.get("kind", "every"),
                at_ms=schedule_data.get("at_ms"),
                every_ms=schedule_data.get("every_ms"),
                expr=schedule_data.get("expr"),
                tz=schedule_data.get("tz"),
            )

            job = self._cron_service.add_job(
                name=name,
                schedule=schedule,
                message=message,
                deliver=data.get("deliver", False),
                channel=data.get("channel"),
                to=data.get("to"),
                delete_after_run=data.get("delete_after_run", False),
            )

            self.notify(FacadeEvent(
                type=FacadeEventType.CREATED,
                resource_type="cron",
                resource_id=job.id,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Cron job '{name}' created", {"id": job.id})
        except Exception as e:
            logger.error("Failed to create cron job: {}", e)
            return OperationResult.error(f"Failed to create cron job: {e}")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        job = self._cron_service.get_job(identifier)
        if not job:
            return OperationResult.error(f"Cron job '{identifier}' not found")

        try:
            if "name" in data:
                job.name = data["name"]
            if "enabled" in data:
                self._cron_service.enable_job(identifier, data["enabled"])
            if "message" in data:
                job.payload.message = data["message"]
            if "deliver" in data:
                job.payload.deliver = data["deliver"]
            if "channel" in data:
                job.payload.channel = data["channel"]
            if "to" in data:
                job.payload.to = data["to"]

            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="cron",
                resource_id=identifier,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Cron job '{identifier}' updated")
        except Exception as e:
            return OperationResult.error(f"Failed to update cron job: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """删除 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        removed = self._cron_service.remove_job(identifier)
        if removed:
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="cron",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Cron job '{identifier}' deleted")

        return OperationResult.error(f"Cron job '{identifier}' not found")

    async def start(self, identifier: str) -> OperationResult:
        """启用 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        job = self._cron_service.enable_job(identifier, True)
        if job:
            self.notify(FacadeEvent(
                type=FacadeEventType.STARTED,
                resource_type="cron",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Cron job '{identifier}' enabled")

        return OperationResult.error(f"Cron job '{identifier}' not found")

    async def stop(self, identifier: str) -> OperationResult:
        """禁用 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        job = self._cron_service.enable_job(identifier, False)
        if job:
            self.notify(FacadeEvent(
                type=FacadeEventType.STOPPED,
                resource_type="cron",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Cron job '{identifier}' disabled")

        return OperationResult.error(f"Cron job '{identifier}' not found")

    async def run(self, identifier: str) -> OperationResult:
        """手动触发 Cron 任务。"""
        if not self._cron_service:
            return OperationResult.error("CronService not available")

        success = await self._cron_service.run_job(identifier, force=True)
        if success:
            return OperationResult.ok(f"Cron job '{identifier}' executed")
        return OperationResult.error(f"Cron job '{identifier}' not found")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 Cron 服务健康状态。"""
        if not self._cron_service:
            return HealthCheckResult.unhealthy("CronService not initialized")

        status = self._cron_service.status()
        return HealthCheckResult.healthy(
            f"Cron service running, {status.get('jobs', 0)} jobs",
            details=status,
        )

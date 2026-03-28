"""
facade/plans/manager.py - PlansFacade

Plans 看板管理接口。
设计原则：
- 持有 bot_id，通过 extension/plans.py 操作持久化
- 不直接操作 nanobot
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class PlansFacade(BaseManager[dict[str, Any]]):
    """
    Plans 看板管理门面。

    职责：
    - 读写 Plans 看板数据（通过 extension/plans）
    - 提供任务 CRUD

    设计原则：
    - 仅通过 extension/plans 与持久化交互
    - 不涉及 nanobot 运行时
    """

    DEFAULT_COLUMNS = [
        {"id": "col-backlog", "title": "待办", "order": 0},
        {"id": "col-progress", "title": "进行中", "order": 1},
        {"id": "col-done", "title": "已完成", "order": 2},
    ]

    def __init__(self, bot_id: str) -> None:
        super().__init__(bot_id)

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """获取整个看板数据。"""
        return [self._get_board()]

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取看板详情。"""
        return self._get_board()

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """保存整个看板数据。"""
        try:
            from console.server.extension.plans import save_plans as _save
            _save(self.bot_id, data)
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="plans",
                resource_id=identifier or "board",
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok("Plans board saved", data)
        except Exception as e:
            return OperationResult.error(f"Failed to save plans: {e}")

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """保存整个看板数据（create 与 update 合并）。"""
        return await self.update("board", data)

    async def delete(self, identifier: str) -> OperationResult:
        """删除任务。"""
        try:
            from console.server.extension.plans import get_plans as _get, save_plans as _save
            board = _get(self.bot_id)
            tasks = [t for t in board.get("tasks", []) if t.get("id") != identifier]
            board["tasks"] = tasks
            _save(self.bot_id, board)
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="plans_task",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Task '{identifier}' deleted")
        except Exception as e:
            return OperationResult.error(f"Failed to delete task: {e}")

    # -------------------------------------------------------------------------
    # 任务 CRUD
    # -------------------------------------------------------------------------

    async def create_task(self, data: dict[str, Any]) -> OperationResult:
        """创建新任务。"""
        try:
            from console.server.extension.plans import get_plans as _get, save_plans as _save
            board = _get(self.bot_id)
            now = time.time()
            task_id = f"task-{int(now * 1000)}"
            now_str = time.strftime("%Y-%m-%dT%H:%M:%S")

            new_task: dict[str, Any] = {
                "id": task_id,
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "columnId": data.get("columnId", "col-backlog"),
                "order": len([t for t in board.get("tasks", []) if t.get("columnId") == data.get("columnId", "col-backlog")]),
                "createdAt": now_str,
                "updatedAt": now_str,
            }
            for key in ("priority", "startDate", "dueDate", "progress", "project"):
                if key in data:
                    new_task[key] = data[key]

            board.setdefault("tasks", []).append(new_task)
            _save(self.bot_id, board)
            self.notify(FacadeEvent(
                type=FacadeEventType.CREATED,
                resource_type="plans_task",
                resource_id=task_id,
                bot_id=self.bot_id,
                data=new_task,
            ))
            return OperationResult.ok(f"Task created", {"id": task_id, "task": new_task})
        except Exception as e:
            return OperationResult.error(f"Failed to create task: {e}")

    async def update_task(self, task_id: str, data: dict[str, Any]) -> OperationResult:
        """更新任务。"""
        try:
            from console.server.extension.plans import get_plans as _get, save_plans as _save
            board = _get(self.bot_id)
            tasks = board.get("tasks", [])
            task = next((t for t in tasks if t.get("id") == task_id), None)
            if not task:
                return OperationResult.error(f"Task '{task_id}' not found")

            for key in ("title", "description", "columnId", "priority", "startDate", "dueDate", "progress", "project"):
                if key in data:
                    task[key] = data[key]
            task["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")

            board["tasks"] = tasks
            _save(self.bot_id, board)
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="plans_task",
                resource_id=task_id,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Task '{task_id}' updated", {"task": task})
        except Exception as e:
            return OperationResult.error(f"Failed to update task: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """Plans 是纯数据层，总是健康。"""
        return HealthCheckResult.healthy("Plans facade available", details={"bot_id": self.bot_id})

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _get_board(self) -> dict[str, Any]:
        """获取看板数据。"""
        if self.bot_id == "_empty":
            return {
                "id": "board-default",
                "name": "默认看板",
                "columns": self.DEFAULT_COLUMNS,
                "tasks": [],
            }
        try:
            from console.server.extension.plans import get_plans as _get
            return _get(self.bot_id)
        except Exception as e:
            logger.debug("Failed to get plans for bot '{}': {}", self.bot_id, e)
            return {
                "id": f"board-{self.bot_id}",
                "name": "看板",
                "columns": self.DEFAULT_COLUMNS,
                "tasks": [],
            }

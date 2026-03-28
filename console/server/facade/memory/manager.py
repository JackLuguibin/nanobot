"""
facade/memory/manager.py - MemoryFacade

长期记忆管理接口。
设计原则：
- 持有 workspace，通过 MemoryStore 操作
- 不涉及 nanobot 运行时
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class MemoryFacade(BaseManager[dict[str, Any]]):
    """
    长期记忆管理门面。

    职责：
    - 读取 MEMORY.md 和 HISTORY.md
    - 写入 MEMORY.md

    设计原则：
    - 仅操作文件系统
    - 不涉及 nanobot 运行时
    """

    def __init__(self, bot_id: str, workspace: Path | None = None) -> None:
        super().__init__(bot_id)
        self._workspace = workspace

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出记忆文件。"""
        if not self._workspace:
            return []
        try:
            from nanobot.agent.memory import MemoryStore
            store = MemoryStore(self._workspace)
            return [
                {"name": "long_term", "path": "MEMORY.md", "exists": store.memory_file.exists()},
                {"name": "history", "path": "HISTORY.md", "exists": store.history_file.exists()},
            ]
        except Exception as e:
            logger.debug("Failed to list memory files: {}", e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """读取记忆内容。identifier = 'long_term' or 'history'。"""
        if not self._workspace:
            return None
        try:
            from nanobot.agent.memory import MemoryStore
            store = MemoryStore(self._workspace)
            if identifier == "long_term":
                return {"name": "long_term", "content": store.read_long_term()}
            elif identifier == "history":
                content = ""
                if store.history_file.exists():
                    content = store.history_file.read_text(encoding="utf-8")
                return {"name": "history", "content": content}
        except Exception as e:
            logger.debug("Failed to read memory '{}': {}", identifier, e)
        return None

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新记忆内容。"""
        if identifier != "long_term":
            return OperationResult.error("Only long_term memory can be updated")

        if not self._workspace:
            return OperationResult.error("Workspace not available")

        try:
            from nanobot.agent.memory import MemoryStore
            store = MemoryStore(self._workspace)
            store.write_long_term(data.get("content", ""))
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="memory",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok("Memory updated")
        except Exception as e:
            return OperationResult.error(f"Failed to update memory: {e}")

    async def create(self, data: dict[str, Any]) -> OperationResult:
        return OperationResult.error("Use update to write memory content")

    async def delete(self, identifier: str) -> OperationResult:
        return OperationResult.error("Deleting memory is not supported")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查记忆系统状态。"""
        if not self._workspace:
            return HealthCheckResult.unknown("Workspace not set")
        return HealthCheckResult.healthy(
            "Memory facade available",
            details={"workspace": str(self._workspace)}
        )

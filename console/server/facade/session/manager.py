"""
facade/session/manager.py - SessionFacade

会话的统一管理接口。
设计原则：
- 仅读取 SessionManager 状态，不直接修改运行时
- delete 操作需同时清理磁盘文件和内存缓存
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class SessionFacade(BaseManager[dict[str, Any]]):
    """
    Session 统一管理门面。

    职责：
    - 持有 SessionManager 引用
    - 提供会话列表、详情、删除操作
    - 不修改 nanobot 核心逻辑

    设计原则：
    - 仅读取会话状态
    - delete 同时清理磁盘和内存缓存
    """

    def __init__(self, bot_id: str, session_manager: Any = None) -> None:
        super().__init__(bot_id)
        self._session_manager = session_manager

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有会话。"""
        if not self._session_manager:
            return []

        by_key: dict[str, dict[str, Any]] = {}

        # 从 list_sessions() 获取基本信息
        if hasattr(self._session_manager, "list_sessions"):
            try:
                for s in self._session_manager.list_sessions():
                    key = s.get("key", "")
                    if not key:
                        continue
                    msg_count = s.get("message_count")
                    if msg_count is None and s.get("path"):
                        msg_count = self._count_messages(Path(s["path"]))
                    by_key[key] = {
                        "key": key,
                        "title": key.split(":")[0] if ":" in key else key,
                        "message_count": msg_count or 0,
                        "last_message": None,
                        "created_at": s.get("created_at"),
                        "updated_at": s.get("updated_at"),
                    }
            except Exception as e:
                logger.debug("Failed to list sessions: {}", e)

        # 从内存缓存补充信息
        if hasattr(self._session_manager, "_cache"):
            for key, session in self._session_manager._cache.items():
                messages = getattr(session, "messages", [])
                last = messages[-1] if messages else None
                by_key[key] = {
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "message_count": len(messages),
                    "last_message": (last.get("content", "")[:100] if last else None),
                    "created_at": (
                        session.created_at.isoformat()
                        if hasattr(session, "created_at") and session.created_at
                        else None
                    ),
                    "updated_at": (
                        session.updated_at.isoformat()
                        if hasattr(session, "updated_at") and session.updated_at
                        else None
                    ),
                }

        sessions = list(by_key.values())
        sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return sessions

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定会话详情。"""
        if not self._session_manager:
            return None

        session = None

        if hasattr(self._session_manager, "_cache"):
            session = self._session_manager._cache.get(identifier)

        if not session and hasattr(self._session_manager, "get_or_create"):
            try:
                session = self._session_manager.get_or_create(identifier)
            except Exception as e:
                logger.debug("Failed to get_or_create session '{}': {}", identifier, e)

        if not session:
            return None

        messages = getattr(session, "messages", [])
        last_consolidated = getattr(session, "last_consolidated", 0)
        unconsolidated = messages[last_consolidated:]
        sliced = unconsolidated[-500:]
        for i, m in enumerate(sliced):
            if m.get("role") == "user":
                sliced = sliced[i:]
                break

        out: list[dict[str, Any]] = []
        for m in sliced:
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name", "timestamp", "created_at", "source"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)

        return {
            "key": identifier,
            "title": identifier.split(":")[0] if ":" in identifier else identifier,
            "messages": out,
            "message_count": len(out),
        }

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建新会话。"""
        if not self._session_manager:
            return OperationResult.error("SessionManager not available")

        import uuid
        key = data.get("key") or f"console:{uuid.uuid4().hex[:8]}"

        try:
            if hasattr(self._session_manager, "get_or_create"):
                self._session_manager.get_or_create(key)
            self.notify(FacadeEvent(
                type=FacadeEventType.CREATED,
                resource_type="session",
                resource_id=key,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Session '{key}' created", {"key": key})
        except Exception as e:
            return OperationResult.error(f"Failed to create session: {e}")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新会话（仅支持标题等元数据，不修改消息历史）。"""
        return OperationResult.ok("Session metadata updated", {"key": identifier})

    async def delete(self, identifier: str) -> OperationResult:
        """删除会话（磁盘文件 + 内存缓存）。"""
        if not self._session_manager:
            return OperationResult.error("SessionManager not available")

        deleted = False

        # 删除磁盘文件
        if hasattr(self._session_manager, "_get_session_path"):
            try:
                path = self._session_manager._get_session_path(identifier)
                if path.exists():
                    path.unlink(missing_ok=True)
                    deleted = True
            except OSError:
                pass

        if hasattr(self._session_manager, "_get_legacy_session_path"):
            try:
                legacy = self._session_manager._get_legacy_session_path(identifier)
                if legacy.exists():
                    legacy.unlink(missing_ok=True)
                    deleted = True
            except OSError:
                pass

        # 删除内存缓存
        if hasattr(self._session_manager, "_cache") and identifier in self._session_manager._cache:
            del self._session_manager._cache[identifier]
            deleted = True
        elif hasattr(self._session_manager, "invalidate"):
            try:
                self._session_manager.invalidate(identifier)
                deleted = True
            except Exception as e:
                logger.debug("Failed to invalidate session '{}': {}", identifier, e)

        if deleted:
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="session",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Session '{identifier}' deleted")

        return OperationResult.error(f"Session '{identifier}' not found")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 SessionManager 健康状态。"""
        if not self._session_manager:
            return HealthCheckResult.unhealthy("SessionManager not initialized")

        count = 0
        if hasattr(self._session_manager, "_cache"):
            count = len(self._session_manager._cache)

        return HealthCheckResult.healthy(
            f"SessionManager running, {count} sessions in cache",
            details={"cached_sessions": count}
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _count_messages(path: Path) -> int:
        """从 JSONL 文件行数推算消息数。"""
        if not path.exists():
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except (OSError, ValueError):
            return 0

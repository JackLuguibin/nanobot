"""
facade/workspace/manager.py - WorkspaceFacade

工作区文件管理接口。
设计原则：
- 仅读取/写入 workspace 目录下的文件
- 不涉及 nanobot 核心逻辑
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class WorkspaceFacade(BaseManager[dict[str, Any]]):
    """
    Workspace 文件管理门面。

    职责：
    - 列出工作区文件
    - 读写工作区文件
    - Bot 配置文件管理

    设计原则：
    - 严格限制在 workspace 目录内
    - 不涉及 nanobot 运行时
    """

    BOT_FILE_KEYS = {
        "soul": "SOUL.md",
        "user": "USER.md",
        "heartbeat": "HEARTBEAT.md",
        "tools": "TOOLS.md",
        "agents": "AGENTS.md",
    }

    def __init__(self, bot_id: str, workspace: Path | None = None) -> None:
        super().__init__(bot_id)
        self._workspace = workspace

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出工作区根目录。"""
        if not self._workspace or not self._workspace.exists():
            return []
        return self._list_dir(self._workspace, depth=1)

    def get(self, identifier: str) -> dict[str, Any] | None:
        """读取 workspace 文件内容。"""
        if not self._workspace:
            return None
        path = self._resolve_path(identifier)
        if path is None or not path.exists() or not path.is_file():
            return None
        try:
            content = path.read_text(encoding="utf-8")
            return {"path": identifier, "content": content, "size": path.stat().st_size}
        except Exception as e:
            logger.debug("Failed to read workspace file '{}': {}", identifier, e)
            return None

    def _list_dir(self, p: Path, depth: int = 1) -> list[dict[str, Any]]:
        """递归列出目录。"""
        if depth <= 0:
            return []
        items = []
        try:
            for child in sorted(p.iterdir()):
                name = child.name
                if name.startswith(".") and name != ".env":
                    continue
                rel = child.relative_to(self._workspace)
                children = None
                if child.is_dir() and depth > 1:
                    children = self._list_dir(child, depth - 1)
                items.append({
                    "name": name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": child.is_dir(),
                    "children": children,
                })
        except PermissionError:
            pass
        return items

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建新文件。"""
        if not self._workspace:
            return OperationResult.error("Workspace not available")

        path_rel = data.get("path", "")
        path = self._resolve_path(path_rel)
        if path is None:
            return OperationResult.error("Invalid path: escapes workspace")
        if path.exists():
            return OperationResult.error("File already exists")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data.get("content", ""), encoding="utf-8")
            return OperationResult.ok(f"File '{path_rel}' created", {"path": path_rel})
        except Exception as e:
            return OperationResult.error(f"Failed to create file: {e}")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新文件内容。"""
        if not self._workspace:
            return OperationResult.error("Workspace not available")

        path = self._resolve_path(identifier)
        if path is None:
            return OperationResult.error("Invalid path")
        if not path.exists():
            return OperationResult.error("File not found")

        try:
            path.write_text(data.get("content", ""), encoding="utf-8")
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="workspace_file",
                resource_id=identifier,
                bot_id=self.bot_id,
                data={"path": identifier},
            ))
            return OperationResult.ok(f"File '{identifier}' updated", {"path": identifier})
        except Exception as e:
            return OperationResult.error(f"Failed to update file: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """删除文件。"""
        if not self._workspace:
            return OperationResult.error("Workspace not available")

        path = self._resolve_path(identifier)
        if path is None or not path.exists():
            return OperationResult.error("File not found")

        try:
            path.unlink()
            return OperationResult.ok(f"File '{identifier}' deleted")
        except Exception as e:
            return OperationResult.error(f"Failed to delete file: {e}")

    # -------------------------------------------------------------------------
    # Bot 配置文件操作
    # -------------------------------------------------------------------------

    async def get_bot_files(self) -> dict[str, str]:
        """读取所有 bot 配置文件（SOUL, USER, HEARTBEAT, TOOLS, AGENTS）。"""
        if not self._workspace:
            return {}
        return {
            key: self._read_file(self._workspace / filename)
            for key, filename in self.BOT_FILE_KEYS.items()
        }

    async def update_bot_file(self, key: str, content: str) -> OperationResult:
        """更新 bot 配置文件。"""
        if key not in self.BOT_FILE_KEYS:
            return OperationResult.error(f"Invalid key. Must be one of: {list(self.BOT_FILE_KEYS.keys())}")
        if not self._workspace:
            return OperationResult.error("Workspace not available")

        path = self._workspace / self.BOT_FILE_KEYS[key]
        try:
            path.write_text(content, encoding="utf-8")
            return OperationResult.ok(f"Bot file '{key}' updated", {"key": key})
        except Exception as e:
            return OperationResult.error(f"Failed to update bot file: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 workspace 状态。"""
        if not self._workspace:
            return HealthCheckResult.unknown("Workspace not set")
        if not self._workspace.exists():
            return HealthCheckResult.unhealthy("Workspace does not exist")
        return HealthCheckResult.healthy(
            f"Workspace accessible: {self._workspace}",
            details={"path": str(self._workspace)}
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _resolve_path(self, rel_path: str) -> Path | None:
        """解析相对路径，确保不超出 workspace。"""
        if not self._workspace:
            return None
        try:
            if rel_path == "." or rel_path == "":
                return self._workspace
            resolved = (self._workspace / rel_path).resolve()
            if not str(resolved).startswith(str(self._workspace.resolve())):
                return None
            return resolved
        except (OSError, ValueError):
            return None

    def _read_file(self, path: Path) -> str:
        """安全读取文件。"""
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

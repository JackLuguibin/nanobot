"""
facade/env/manager.py - EnvFacade

环境变量管理接口。
设计原则：
- 持有 bot_id，读取/写入 .env 文件
- 不涉及 nanobot 核心逻辑
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class EnvFacade(BaseManager[dict[str, Any]]):
    """
    环境变量管理门面。

    职责：
    - 读取 .env 文件
    - 写入 .env 文件

    设计原则：
    - 直接操作文件系统
    - 不涉及 nanobot 运行时
    """

    def __init__(self, bot_id: str, config_path: Path | None = None) -> None:
        super().__init__(bot_id)
        self._config_path = config_path

    def _get_env_path(self) -> Path | None:
        """获取 .env 文件路径。"""
        if self.bot_id == "_empty" or self._config_path is None:
            return None
        return self._config_path.parent / ".env"

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有环境变量。"""
        path = self._get_env_path()
        if not path or not path.exists():
            return []

        try:
            from dotenv import dotenv_values
            vars_dict = dotenv_values(path)
            return [{"key": k, "value": v or ""} for k, v in vars_dict.items()]
        except Exception as e:
            logger.debug("Failed to read .env: {}", e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定环境变量。"""
        path = self._get_env_path()
        if not path or not path.exists():
            return None

        try:
            from dotenv import dotenv_values
            vars_dict = dotenv_values(path)
            value = vars_dict.get(identifier)
            if value is None:
                return None
            return {"key": identifier, "value": value}
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新单个环境变量。"""
        return await self.update_batch({identifier: data.get("value", "")})

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """批量更新环境变量。"""
        return await self.update_batch(data)

    async def update_batch(self, vars_dict: dict[str, str]) -> OperationResult:
        """批量更新环境变量。"""
        path = self._get_env_path()
        if not path:
            return OperationResult.error("No bot config path available")

        path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有变量
        existing: dict[str, str] = {}
        if path.exists():
            try:
                from dotenv import dotenv_values
                existing = {k: (v or "") for k, v in dotenv_values(path).items()}
            except Exception:
                pass

        # 更新变量
        for key, value in vars_dict.items():
            if not key or "=" in key or "\n" in key:
                continue
            if not isinstance(value, str):
                value = str(value)
            existing[key] = value

        # 写入
        lines: list[str] = []
        for key, value in existing.items():
            if " " in value or "\n" in value or '"' in value or "=" in value or "#" in value:
                escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'{key}="{escaped}"')
            else:
                lines.append(f"{key}={value}")

        try:
            path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write .env: {}", e)
            return OperationResult.error(f"Failed to save .env: {e}")

        self.notify(FacadeEvent(
            type=FacadeEventType.UPDATED,
            resource_type="env",
            resource_id="dotenv",
            bot_id=self.bot_id,
            data={"updated": list(vars_dict.keys())},
        ))
        return OperationResult.ok("Environment variables updated", {"updated": list(vars_dict.keys())})

    async def delete(self, identifier: str) -> OperationResult:
        """删除环境变量（设置为空字符串）。"""
        return await self.update_batch({identifier: ""})

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 .env 文件状态。"""
        path = self._get_env_path()
        if path is None:
            return HealthCheckResult.unknown("No config path available")
        if not path.exists():
            return HealthCheckResult.unknown(".env file does not exist yet")
        return HealthCheckResult.healthy(f".env accessible at {path}", details={"path": str(path)})

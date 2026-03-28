"""
facade/config/manager.py - ConfigFacade

配置统一管理接口。
设计原则：
- 持有 ConfigBridge 引用
- 提供配置读取、写入、Schema、验证
- 通过 ConfigBridge 保证配置一致性
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class ConfigFacade(BaseManager[dict[str, Any]]):
    """
    配置统一管理门面。

    职责：
    - 提供配置的 CRUD 操作
    - 提供配置 Schema 和验证
    - 通过 ConfigBridge 读写配置文件

    设计原则：
    - 配置变更通过 ConfigBridge
    - 验证失败不保存
    """

    def __init__(
        self,
        bot_id: str,
        config_bridge: Any = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(bot_id)
        self._config_bridge = config_bridge
        self._config = config or {}

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有顶层配置节。"""
        return [
            {"name": name, "keys": list(value.keys()) if isinstance(value, dict) else []}
            for name, value in self._config.items()
        ]

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定配置节。"""
        return self._config.get(identifier)

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def update(self, section: str, data: dict[str, Any]) -> OperationResult:
        """更新配置节。"""
        if not self._config_bridge:
            async with self._lock:
                if section not in self._config:
                    self._config[section] = {}
                self._config[section].update(data)
                self._save_config()
            self.notify(FacadeEvent(
                type=FacadeEventType.CONFIG_CHANGED,
                resource_type="config",
                resource_id=section,
                bot_id=self.bot_id,
                data={"section": section, "changes": data},
            ))
            return OperationResult.ok(f"Config section '{section}' updated")

        try:
            current = self._config_bridge.load_raw()
            if section not in current:
                current[section] = {}
            current[section].update(data)
            errors = self._config_bridge.validate(current)
            if errors:
                return OperationResult.error(f"Validation failed: {'; '.join(errors)}")
            self._config_bridge.save(current)
            self._config = current
            self.notify(FacadeEvent(
                type=FacadeEventType.CONFIG_CHANGED,
                resource_type="config",
                resource_id=section,
                bot_id=self.bot_id,
                data={"section": section, "changes": data},
            ))
            return OperationResult.ok(f"Config section '{section}' updated")
        except Exception as e:
            logger.error("Failed to update config section '{}': {}", section, e)
            return OperationResult.error(f"Failed to update config: {e}")

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建/覆盖整个配置（谨慎使用）。"""
        if not self._config_bridge:
            return OperationResult.error("ConfigBridge not available")

        try:
            errors = self._config_bridge.validate(data)
            if errors:
                return OperationResult.error(f"Validation failed: {'; '.join(errors)}")
            self._config_bridge.save(data)
            self._config = data
            self.notify(FacadeEvent(
                type=FacadeEventType.CONFIG_CHANGED,
                resource_type="config",
                resource_id="full",
                bot_id=self.bot_id,
                data={"action": "full_replace"},
            ))
            return OperationResult.ok("Config saved")
        except Exception as e:
            return OperationResult.error(f"Failed to save config: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """删除配置节（设置为空字典）。"""
        return await self.update(identifier, {})

    # -------------------------------------------------------------------------
    # 配置工具
    # -------------------------------------------------------------------------

    async def get_schema(self) -> dict[str, Any]:
        """获取配置 Schema。"""
        try:
            from nanobot.config.schema import Config
            return Config.model_json_schema()
        except Exception as e:
            logger.error("Failed to get config schema: {}", e)
            return {"error": str(e)}

    async def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """验证配置数据。"""
        try:
            from nanobot.config.schema import Config
            Config(**data)
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查配置状态。"""
        if not self._config:
            return HealthCheckResult.unknown("No config loaded")
        return HealthCheckResult.healthy(
            f"Config loaded with {len(self._config)} sections",
            details={"sections": list(self._config.keys())}
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _save_config(self) -> None:
        """保存配置到文件。"""
        from console.server.api.state import get_state_manager
        manager = get_state_manager()
        state = manager.get_state(self.bot_id)
        if state.config_path:
            import json
            try:
                state.config_path.write_text(json.dumps(self._config, indent=2, ensure_ascii=False))
            except Exception as e:
                logger.warning("Failed to write config: {}", e)

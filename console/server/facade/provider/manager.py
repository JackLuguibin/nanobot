"""
facade/provider/manager.py - ProviderFacade

LLM Provider 的统一管理接口。
设计原则：
- 仅读取 Provider 状态和配置，不直接修改运行时
- 配置变更通过 ConfigBridge 写入配置文件
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class ProviderFacade(BaseManager[dict[str, Any]]):
    """
    Provider 统一管理门面。

    职责：
    - 持有 ConfigBridge 引用（读取 providers 配置）
    - 提供 Provider 列表、配置读取
    - 配置变更通过 ConfigBridge 写入

    设计原则：
    - 仅读取 Provider 状态
    - 配置变更通过配置文件
    """

    def __init__(self, bot_id: str, config_bridge: Any = None) -> None:
        super().__init__(bot_id)
        self._config_bridge = config_bridge

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有 Provider 配置。"""
        if not self._config_bridge:
            return []

        try:
            raw = self._config_bridge.load_raw()
            providers = raw.get("providers") or {}
            return [
                {
                    "name": name,
                    "config": cfg if isinstance(cfg, dict) else {},
                    "type": self._infer_type(cfg),
                }
                for name, cfg in providers.items()
            ]
        except Exception as e:
            logger.debug("Failed to list providers: {}", e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定 Provider 配置。"""
        if not self._config_bridge:
            return None

        try:
            raw = self._config_bridge.load_raw()
            providers = raw.get("providers") or {}
            cfg = providers.get(identifier)
            if cfg is None:
                return None
            return {
                "name": identifier,
                "config": cfg if isinstance(cfg, dict) else {},
                "type": self._infer_type(cfg),
            }
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 写操作（配置驱动）
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新 Provider 配置（写入配置文件）。"""
        if not self._config_bridge:
            return OperationResult.error("ConfigBridge not available")

        try:
            current = self._config_bridge.load_raw()
            providers = current.get("providers", {})
            if identifier not in providers:
                providers[identifier] = {}
            providers[identifier].update(data)
            current["providers"] = providers

            errors = self._config_bridge.validate(current)
            if errors:
                return OperationResult.error(f"Config validation failed: {'; '.join(errors)}")

            self._config_bridge.save(current)
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="provider",
                resource_id=identifier,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Provider '{identifier}' updated")
        except Exception as e:
            return OperationResult.error(f"Failed to update provider: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """删除 Provider 配置（从配置文件中移除）。"""
        if not self._config_bridge:
            return OperationResult.error("ConfigBridge not available")

        try:
            current = self._config_bridge.load_raw()
            providers = current.get("providers", {})
            if identifier not in providers:
                return OperationResult.error(f"Provider '{identifier}' not found")

            del providers[identifier]
            current["providers"] = providers
            self._config_bridge.save(current)
            self.notify(FacadeEvent(
                type=FacadeEventType.DELETED,
                resource_type="provider",
                resource_id=identifier,
                bot_id=self.bot_id,
            ))
            return OperationResult.ok(f"Provider '{identifier}' deleted")
        except Exception as e:
            return OperationResult.error(f"Failed to delete provider: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 Provider 配置状态。"""
        if not self._config_bridge:
            return HealthCheckResult.unhealthy("ConfigBridge not initialized")

        try:
            raw = self._config_bridge.load_raw()
            providers = raw.get("providers") or {}
            agents_defaults = raw.get("agents", {}).get("defaults", {})
            default_provider = agents_defaults.get("provider", "")

            details = {
                "total_providers": len(providers),
                "default_provider": default_provider,
                "provider_names": list(providers.keys()),
            }

            if not providers:
                return HealthCheckResult.unknown("No providers configured", details=details)
            if default_provider and default_provider not in providers:
                return HealthCheckResult.degraded(
                    f"Default provider '{default_provider}' not found", details=details
                )

            return HealthCheckResult.healthy(
                f"{len(providers)} providers configured", details=details
            )
        except Exception as e:
            return HealthCheckResult.unhealthy(f"Failed to load config: {e}")

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _infer_type(config: Any) -> str:
        """从配置推断 Provider 类型。"""
        if not isinstance(config, dict):
            return "unknown"
        if "api_key" in config:
            return "api_key"
        if "azure_endpoint" in config or "azure_api_version" in config:
            return "azure"
        if "base_url" in config or "openai_api_base" in config:
            return "compatible"
        return "unknown"

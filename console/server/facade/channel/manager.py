"""
facade/channel/manager.py - ChannelFacade

通道的统一管理接口。
设计原则：
- 仅通过配置变更影响 nanobot 通道状态
- 不直接调用 ChannelManager 运行时方法（除健康检查外）
- start/stop 通过配置文件写入实现
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class ChannelFacade(BaseManager[dict[str, Any]]):
    """
    Channel 统一管理门面。

    职责：
    - 持有 ChannelManager 和 ConfigBridge 引用
    - 提供通道列表、状态、配置读取
    - 配置变更通过 ConfigBridge 写入配置文件

    设计原则：
    - 仅通过配置驱动与 nanobot 交互
    - 不直接修改 ChannelManager 运行时状态
    """

    CHANNEL_NAMES = (
        "whatsapp", "telegram", "discord", "feishu", "mochat",
        "dingtalk", "email", "slack", "qq", "matrix",
    )

    def __init__(
        self,
        bot_id: str,
        channel_manager: Any = None,
        config_bridge: Any = None,
    ) -> None:
        super().__init__(bot_id)
        self._channel_manager = channel_manager
        self._config_bridge = config_bridge

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有通道。"""
        channels: list[dict[str, Any]] = []
        runtime_by_name: dict[str, dict] = {}

        ch_dict: dict[str, Any] | None = None
        if self._channel_manager:
            ch_dict = getattr(self._channel_manager, "channels", None) or getattr(
                self._channel_manager, "_channels", None
            )
        if ch_dict:
            for name, ch in ch_dict.items():
                runtime_by_name[name] = {
                    "name": name,
                    "status": "online" if getattr(ch, "_connected", False) else "offline",
                    "stats": {},
                }

        config_channels: dict[str, Any] = {}
        if self._config_bridge:
            try:
                raw = self._config_bridge.load_raw()
                config_channels = raw.get("channels") or {}
            except Exception:
                pass

        for name in self.CHANNEL_NAMES:
            cfg = config_channels.get(name) or {}
            enabled = cfg.get("enabled", False) if isinstance(cfg, dict) else False

            if name in runtime_by_name:
                row = dict(runtime_by_name[name])
                row["enabled"] = enabled
            else:
                row = {"name": name, "enabled": enabled, "status": "offline", "stats": {}}
            channels.append(row)

        return channels

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定通道详情。"""
        if identifier not in self.CHANNEL_NAMES:
            return None

        config_channels: dict[str, Any] = {}
        if self._config_bridge:
            try:
                raw = self._config_bridge.load_raw()
                config_channels = raw.get("channels") or {}
            except Exception:
                pass

        cfg = config_channels.get(identifier) or {}

        runtime_status = "offline"
        if self._channel_manager:
            ch = self._channel_manager.get_channel(identifier) if hasattr(self._channel_manager, "get_channel") else None
            if ch:
                runtime_status = "online" if getattr(ch, "_connected", False) else "offline"

        return {
            "name": identifier,
            "enabled": cfg.get("enabled", False) if isinstance(cfg, dict) else False,
            "status": runtime_status,
            "config": cfg if isinstance(cfg, dict) else {},
        }

    # -------------------------------------------------------------------------
    # 写操作（配置驱动）
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新通道配置（写入配置文件）。"""
        if identifier not in self.CHANNEL_NAMES:
            return OperationResult.error(f"Unknown channel: {identifier}")

        if not self._config_bridge:
            return OperationResult.error("ConfigBridge not available")

        try:
            current = self._config_bridge.load_raw()
            channels = current.get("channels", {})
            if identifier not in channels:
                channels[identifier] = {}
            channels[identifier].update(data)
            current["channels"] = channels

            errors = self._config_bridge.validate(current)
            if errors:
                return OperationResult.error(f"Config validation failed: {'; '.join(errors)}")

            self._config_bridge.save(current)

            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="channel",
                resource_id=identifier,
                bot_id=self.bot_id,
                data=data,
            ))
            return OperationResult.ok(f"Channel '{identifier}' updated", {"name": identifier})
        except Exception as e:
            logger.error("Failed to update channel '{}': {}", identifier, e)
            return OperationResult.error(f"Failed to update channel: {e}")

    async def delete(self, identifier: str) -> OperationResult:
        """禁用通道（设置 enabled=False）。"""
        return await self.update(identifier, {"enabled": False})

    async def start(self, identifier: str) -> OperationResult:
        """启用通道（设置 enabled=True）。"""
        return await self.update(identifier, {"enabled": True})

    async def stop(self, identifier: str) -> OperationResult:
        """停止通道（禁用 + 可选运行时停止）。"""
        result = await self.update(identifier, {"enabled": False})

        # 可选：直接停止运行时
        if result.success and self._channel_manager:
            try:
                ch = (self._channel_manager.get_channel(identifier)
                      if hasattr(self._channel_manager, "get_channel") else None)
                if ch and hasattr(ch, "stop"):
                    await ch.stop()
            except Exception as e:
                logger.debug("Stop channel '{}' runtime error: {}", identifier, e)

        return result

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查通道健康状态。"""
        if not self._channel_manager:
            return HealthCheckResult.unhealthy("ChannelManager not initialized")

        channels = getattr(self._channel_manager, "channels", None) or {}
        online = sum(1 for ch in channels.values() if getattr(ch, "_connected", False))
        total = len(channels)

        details = {
            "channels_online": online,
            "channels_total": total,
            "channel_names": list(channels.keys()),
        }

        if total == 0:
            return HealthCheckResult.unknown("No channels configured")
        if online == 0:
            return HealthCheckResult.unhealthy("All channels offline", details=details)
        if online < total:
            return HealthCheckResult.degraded(f"{online}/{total} channels online", details=details)

        return HealthCheckResult.healthy(f"{online}/{total} channels online", details=details)

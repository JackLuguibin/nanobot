"""
extension/gateway_state.py - Gateway 状态观察器

Facade 层通过此模块观察 Gateway（ChannelManager）状态变化。
仅读取 Gateway 状态，不直接调用 Gateway 方法。
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from console.server.gateway.adapter import GatewayAdapter, GatewayEvent
from console.server.gateway.status import GatewayStatus, GatewayRunState


class GatewayBridge:
    """
    Gateway 桥接器（Facade 层视角）。

    职责：
    - 持有 GatewayAdapter 引用
    - 维护状态缓存
    - 管理状态订阅者（Facade 各 Manager）
    - 将 Gateway 事件转换为 FacadeEvent 格式

    设计原则：
    - Gateway 完全自主运行，不依赖后端管理层
    - Facade 仅通过 GatewayBridge 观察 Gateway 状态
    """

    def __init__(self) -> None:
        self._adapter: GatewayAdapter | None = None
        self._status_cache: GatewayStatus | None = None
        self._status_subscribers: list[Callable[[GatewayStatus], None]] = []

    def set_adapter(self, adapter: GatewayAdapter) -> None:
        """设置 Gateway 适配器（生命周期中注入）。"""
        self._adapter = adapter

    def get_cached_status(self) -> GatewayStatus | None:
        """获取缓存的 Gateway 状态。"""
        return self._status_cache

    def refresh_status(self) -> GatewayStatus:
        """
        强制刷新 Gateway 状态并通知订阅者。
        返回最新的 GatewayStatus。
        """
        if self._adapter is None:
            from console.server.gateway.status import GatewayStatus as GS
            return GS(run_state=GatewayRunState.UNKNOWN, message="No adapter")

        status = self._adapter.get_status(force_refresh=True)
        self._status_cache = status

        for cb in self._status_subscribers:
            try:
                cb(status)
            except Exception as e:
                logger.debug("Gateway status subscriber error: {}", e)

        return status

    def get_status(self) -> GatewayStatus:
        """
        获取 Gateway 状态（优先使用缓存）。
        """
        if self._adapter is None:
            from console.server.gateway.status import GatewayStatus as GS
            return GS(run_state=GatewayRunState.UNKNOWN, message="No adapter")

        status = self._adapter.get_status()
        self._status_cache = status
        return status

    def is_running(self) -> bool:
        """Gateway 是否在运行。"""
        status = self.get_status()
        return status.run_state == GatewayRunState.RUNNING

    def subscribe_status(self, callback: Callable[[GatewayStatus], None]) -> None:
        """订阅 Gateway 状态变化。"""
        if callback not in self._status_subscribers:
            self._status_subscribers.append(callback)

    def unsubscribe_status(self, callback: Callable[[GatewayStatus], None]) -> None:
        """取消订阅 Gateway 状态变化。"""
        if callback in self._status_subscribers:
            self._status_subscribers.remove(callback)

    # -------------------------------------------------------------------------
    # Gateway 事件转发
    # -------------------------------------------------------------------------

    def on_gateway_connect(self, event: GatewayEvent) -> None:
        """处理通道连接事件。"""
        logger.info("Gateway channel connected: {}", event.channel_name)
        self.refresh_status()

    def on_gateway_disconnect(self, event: GatewayEvent) -> None:
        """处理通道断开事件。"""
        logger.warning("Gateway channel disconnected: {}", event.channel_name)
        self.refresh_status()

    def on_gateway_message(self, event: GatewayEvent) -> None:
        """处理消息事件。"""
        for cb in self._status_subscribers:
            try:
                cb(event)
            except Exception as e:
                logger.debug("Gateway message subscriber error: {}", e)

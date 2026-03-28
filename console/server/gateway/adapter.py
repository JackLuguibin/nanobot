"""
gateway/adapter.py - Gateway 适配器

职责：
- 与 nanobot ChannelManager 直接通信（仅读取状态）
- 缓存 Gateway 状态
- 订阅 Gateway 事件（通道连接/断开/消息）
- 提供统一的 Gateway 状态接口

设计原则：
- Gateway 完全自主运行，不依赖后端管理层
- 后端仅通过适配器观察 Gateway 状态
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from .status import GatewayStats, GatewayStatus, GatewayRunState, map_channel_manager_status


@dataclass
class GatewayEvent:
    """Gateway 事件（通道连接/断开/消息）。"""
    type: str  # "connected" | "disconnected" | "message"
    channel_name: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class GatewayAdapter:
    """
    Gateway 适配器。

    职责：
    - 持有 nanobot ChannelManager 引用
    - 提供 get_status() / is_running() / get_stats()
    - 管理事件订阅（on_connect / on_disconnect / on_message）

    设计原则：
    - 仅读取，不修改 nanobot 状态
    - 与 nanobot Gateway 直接通信（通过 ChannelManager）
    """

    def __init__(self, channel_manager: Any | None = None) -> None:
        self._channel_manager = channel_manager
        self._cached_status: GatewayStatus = GatewayStatus(
            run_state=GatewayRunState.UNKNOWN,
            message="Not initialized",
        )
        self._status_cache_time: float = 0.0
        self._cache_ttl: float = 5.0  # seconds

        self._on_connect: list[Callable[[GatewayEvent], None]] = []
        self._on_disconnect: list[Callable[[GatewayEvent], None]] = []
        self._on_message: list[Callable[[GatewayEvent], None]] = []

        self._lock = asyncio.Lock()

    def set_channel_manager(self, channel_manager: Any) -> None:
        """设置 ChannelManager（生命周期管理中调用）。"""
        self._channel_manager = channel_manager
        self._invalidate_cache()

    def get_status(self, *, force_refresh: bool = False) -> GatewayStatus:
        """
        获取 Gateway 状态（带缓存，TTL=5s）。
        force_refresh=True 强制刷新。
        """
        import time
        now = time.time()
        if force_refresh or (now - self._status_cache_time) > self._cache_ttl:
            self._refresh_status()
        return self._cached_status

    def is_running(self) -> bool:
        """Gateway 是否在运行。"""
        status = self.get_status()
        return status.run_state == GatewayRunState.RUNNING

    def get_stats(self) -> GatewayStats:
        """获取 Gateway 统计。"""
        return self.get_status().stats

    def _refresh_status(self) -> None:
        """刷新状态缓存。"""
        import time
        self._cached_status = map_channel_manager_status(self._channel_manager)
        self._status_cache_time = time.time()

    def _invalidate_cache(self) -> None:
        """使缓存失效，下次 get_status 时会刷新。"""
        self._status_cache_time = 0.0

    # -------------------------------------------------------------------------
    # 事件订阅
    # -------------------------------------------------------------------------

    def on_connect(self, callback: Callable[[GatewayEvent], None]) -> None:
        """订阅通道连接事件。"""
        if callback not in self._on_connect:
            self._on_connect.append(callback)

    def on_disconnect(self, callback: Callable[[GatewayEvent], None]) -> None:
        """订阅通道断开事件。"""
        if callback not in self._on_disconnect:
            self._on_disconnect.append(callback)

    def on_message(self, callback: Callable[[GatewayEvent], None]) -> None:
        """订阅消息事件。"""
        if callback not in self._on_message:
            self._on_message.append(callback)

    def _emit_connect(self, channel_name: str, data: dict[str, Any] | None = None) -> None:
        event = GatewayEvent(type="connected", channel_name=channel_name, data=data or {})
        for cb in self._on_connect:
            try:
                cb(event)
            except Exception as e:
                logger.debug("Gateway connect callback error: {}", e)

    def _emit_disconnect(self, channel_name: str, data: dict[str, Any] | None = None) -> None:
        event = GatewayEvent(type="disconnected", channel_name=channel_name, data=data or {})
        for cb in self._on_disconnect:
            try:
                cb(event)
            except Exception as e:
                logger.debug("Gateway disconnect callback error: {}", e)

    def _emit_message(self, channel_name: str, data: dict[str, Any] | None = None) -> None:
        event = GatewayEvent(type="message", channel_name=channel_name, data=data or {})
        for cb in self._on_message:
            try:
                cb(event)
            except Exception as e:
                logger.debug("Gateway message callback error: {}", e)

"""
extension/event_bridge.py - 事件桥接

Facade 层通过此模块订阅 nanobot 内部事件。
目前主要通过 WebSocket 广播来自 extension 层的事件。
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger


class EventBridge:
    """
    事件桥接器。

    职责：
    - 作为 Facade 层与 extension 层之间的轻量级事件总线
    - extension 层发布事件，Facade 层订阅处理
    - 与 nanobot 内部事件系统隔离

    设计原则：
    - 仅作为 Facade 内部的事件转发，不依赖 nanobot 内部事件
    - extension 层通过 facade_event 机制通知 Facade 层状态变化
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """订阅事件主题。"""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if callback not in self._subscribers[topic]:
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """取消订阅事件主题。"""
        if topic in self._subscribers and callback in self._subscribers[topic]:
            self._subscribers[topic].remove(callback)

    def publish(self, topic: str, data: dict[str, Any]) -> None:
        """发布事件到指定主题。"""
        for callback in self._subscribers.get(topic, []):
            try:
                callback(data)
            except Exception as e:
                logger.debug("EventBridge callback error on topic '{}': {}", topic, e)

    def has_subscribers(self, topic: str) -> bool:
        """检查是否有订阅者。"""
        return len(self._subscribers.get(topic, [])) > 0

"""
facade/state/watcher.py - 状态变化监视器

监听各 Facade Manager 的状态变化事件。
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger


class StateWatcher:
    """
    状态变化监视器。

    职责：
    - 监听所有 Facade Manager 的 FacadeEvent
    - 聚合状态变化并通知订阅者
    - 防止短时间内重复通知（防抖）
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._last_event_time: float = 0.0
        self._debounce_ms: float = 500.0

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """注册状态变化监听器。"""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """取消状态变化监听器。"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def on_facade_event(self, event: dict[str, Any]) -> None:
        """处理来自各 Manager 的 FacadeEvent。"""
        import time
        now = time.time()
        if (now - self._last_event_time) * 1000 < self._debounce_ms:
            logger.debug("StateWatcher: debounce skip event {}", event.get("type"))
            return

        self._last_event_time = now

        for cb in self._subscribers:
            try:
                cb(event)
            except Exception as e:
                logger.debug("StateWatcher subscriber error: {}", e)

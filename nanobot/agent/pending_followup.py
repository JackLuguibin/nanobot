"""Mid-turn follow-up buffer: newest messages are injected first (LIFO batch selection)."""

from __future__ import annotations

import asyncio
from collections import deque

from nanobot.bus.events import InboundMessage


class PendingFollowupBuffer:
    """Queue follow-ups for the active session; drain for injection prefers the newest entries.

    - *Storage*: append to the right (chronological: left = oldest).
    - *Injection drain*: take up to *limit* messages from the **right** (newest first), then
      reverse so the batch passed to the model is **oldest-first within the batch** (natural
      dialogue order among those lines).
    - *Re-publish* (when dispatch ends): drain **oldest-first** (full chronological order).
    """

    __slots__ = ("_maxsize", "_dq")

    def __init__(self, maxsize: int = 20) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = maxsize
        self._dq: deque[InboundMessage] = deque()  # left=oldest, right=newest

    def __len__(self) -> int:
        return len(self._dq)

    def qsize(self) -> int:
        return len(self._dq)

    def empty(self) -> bool:
        return len(self._dq) == 0

    def put_nowait(self, msg: InboundMessage) -> None:
        if len(self._dq) >= self._maxsize:
            raise asyncio.QueueFull
        self._dq.append(msg)

    def get_nowait(self) -> InboundMessage:
        """Remove and return the **oldest** message (FIFO single-item pop, for tests / compatibility)."""
        if not self._dq:
            raise asyncio.QueueEmpty
        return self._dq.popleft()

    def pop_batch_newest_priority_chrono(self, limit: int) -> list[InboundMessage]:
        """Pop up to *limit* messages, preferring newest; return oldest-first within the batch."""
        k = min(limit, len(self._dq))
        popped: list[InboundMessage] = []
        for _ in range(k):
            popped.append(self._dq.pop())
        popped.reverse()
        return popped

    def drain_all_oldest_first(self) -> list[InboundMessage]:
        """Remove all messages in chronological order (for re-publishing to the bus)."""
        out: list[InboundMessage] = []
        while self._dq:
            out.append(self._dq.popleft())
        return out

"""Tests for PendingFollowupBuffer (newest-first injection selection)."""

from __future__ import annotations

import asyncio

import pytest

from nanobot.agent.pending_followup import PendingFollowupBuffer
from nanobot.bus.events import InboundMessage


def _msg(content: str) -> InboundMessage:
    return InboundMessage(channel="cli", sender_id="u", chat_id="c", content=content)


def test_put_full_raises_queue_full() -> None:
    b = PendingFollowupBuffer(maxsize=1)
    b.put_nowait(_msg("a"))
    with pytest.raises(asyncio.QueueFull):
        b.put_nowait(_msg("b"))


def test_pop_batch_prefers_newest() -> None:
    b = PendingFollowupBuffer(maxsize=20)
    for c in ("m0", "m1", "m2"):
        b.put_nowait(_msg(c))
    batch = b.pop_batch_newest_priority_chrono(2)
    assert [m.content for m in batch] == ["m1", "m2"]
    assert len(b) == 1
    assert b.get_nowait().content == "m0"


def test_drain_all_oldest_first() -> None:
    b = PendingFollowupBuffer(maxsize=20)
    for c in ("a", "b", "c"):
        b.put_nowait(_msg(c))
    drained = b.drain_all_oldest_first()
    assert [m.content for m in drained] == ["a", "b", "c"]
    assert b.empty()

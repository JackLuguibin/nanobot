"""Tests for auto wiki-archive when estimated prompt crosses a context fraction threshold."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.session.manager import Session


@pytest.mark.asyncio
async def test_maybe_auto_wiki_archive_disabled_returns_none(tmp_path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.generation.max_tokens = 4096
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test/model",
        context_window_tokens=100_000,
        auto_wiki_archive_at_context_fraction=None,
    )
    sess = Session(key="cli:t")
    sess.messages = [{"role": "user", "content": "hi", "timestamp": "2026-01-01T00:00:00"}]
    msg = InboundMessage(channel="cli", sender_id="u", chat_id="t", content="hello")
    out = await loop._maybe_auto_wiki_archive(msg, sess, None)
    assert out is None


@pytest.mark.asyncio
async def test_maybe_auto_wiki_archive_skips_when_below_threshold(tmp_path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.generation.max_tokens = 4096
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test/model",
        context_window_tokens=10_000,
        auto_wiki_archive_at_context_fraction=0.8,
    )
    loop._estimate_inbound_prompt_tokens = MagicMock(return_value=(100, "mock"))  # type: ignore[method-assign]

    sess = Session(key="cli:t")
    msg = InboundMessage(channel="cli", sender_id="u", chat_id="t", content="hello")
    out = await loop._maybe_auto_wiki_archive(msg, sess, None)
    assert out is None


@pytest.mark.asyncio
async def test_maybe_auto_wiki_archive_triggers_ingest_path(tmp_path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.generation.max_tokens = 4096
    provider.chat_with_retry = AsyncMock(
        return_value=MagicMock(
            content='[{"category_slug": "t1", "display_title": "T", "entry_markdown": "## Summary\\n\\nBody."}]',
        ),
    )
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test/model",
        context_window_tokens=1000,
        auto_wiki_archive_at_context_fraction=0.5,
    )
    loop._estimate_inbound_prompt_tokens = MagicMock(return_value=(900, "mock"))  # type: ignore[method-assign]

    sess = Session(key="cli:t")
    sess.messages = [{"role": "user", "content": "prior", "timestamp": "2026-01-01T00:00:00"}]
    msg = InboundMessage(channel="cli", sender_id="u", chat_id="t", content="current turn")
    out = await loop._maybe_auto_wiki_archive(msg, sess, None)
    assert out is not None
    assert "Auto wiki-archive" in (out.content or "")
    assert (tmp_path / "wiki" / "t1.md").is_file()


def test_agent_defaults_rejects_invalid_auto_wiki_fraction() -> None:
    from pydantic import ValidationError

    from nanobot.config.schema import AgentDefaults

    with pytest.raises(ValidationError):
        AgentDefaults(auto_wiki_archive_at_context_fraction=0.0)
    with pytest.raises(ValidationError):
        AgentDefaults(auto_wiki_archive_at_context_fraction=1.1)

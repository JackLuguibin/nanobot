"""Tests for /wiki-archive command."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import MemoryStore
from nanobot.command.builtin import cmd_wiki_archive
from nanobot.command.router import CommandContext
from nanobot.session.manager import Session


def _mock_loop_bus(loop: MagicMock) -> None:
    loop.bus = MagicMock()
    loop.bus.publish_outbound = AsyncMock()


@pytest.mark.asyncio
async def test_cmd_wiki_archive_skips_empty_model_output(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    loop = MagicMock()
    _mock_loop_bus(loop)
    loop.consolidator.store = store
    loop.model = "test/model"
    loop.provider.chat_with_retry = AsyncMock(
        return_value=MagicMock(
            content="CATEGORY_SLUG: empty-session\n\n# (empty session)\n",
        ),
    )
    sess = Session(key="cli:t")
    sess.messages = [{"role": "user", "content": "x", "timestamp": "2026-04-11T10:00:00"}]
    sess.last_consolidated = 0
    loop.sessions.get_or_create.return_value = sess

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=sess, key="cli:t", raw="/wiki-archive", loop=loop)

    out = await cmd_wiki_archive(ctx)
    assert "Nothing to archive" in out.content
    assert not list((tmp_path / "wiki").glob("*.md"))


@pytest.mark.asyncio
async def test_cmd_wiki_archive_empty_session(tmp_path: Path) -> None:
    loop = MagicMock()
    loop.sessions.get_or_create.return_value = MagicMock(
        messages=[], last_consolidated=0,
    )
    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=None, key="cli:t", raw="/wiki-archive", loop=loop)

    out = await cmd_wiki_archive(ctx)
    assert "No messages to archive" in out.content


@pytest.mark.asyncio
async def test_cmd_wiki_archive_writes_wiki_and_replaces_session(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    loop = MagicMock()
    _mock_loop_bus(loop)
    loop.consolidator.store = store
    loop.model = "test/model"

    async def chat_with_retry(**kwargs):
        r = MagicMock()
        r.content = (
            "CATEGORY_SLUG: routing-db\n"
            "DISPLAY_TITLE: Routing discussion\n"
            "\n"
            "## Summary\n\n"
            "Chose PostgreSQL over SQLite for concurrent writes.\n\n"
            "## Notes\n\n"
            "- See `db/migrate`\n"
        )
        return r

    loop.provider.chat_with_retry = AsyncMock(side_effect=chat_with_retry)

    sess = Session(key="cli:t")
    sess.messages = [
        {"role": "user", "content": "hi", "timestamp": "2026-04-11T10:00:00"},
    ]
    sess.last_consolidated = 0
    loop.sessions.get_or_create.return_value = sess
    loop.sessions.save = MagicMock()
    loop.sessions.invalidate = MagicMock()

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=sess, key="cli:t", raw="/wiki-archive", loop=loop)

    out = await cmd_wiki_archive(ctx)
    assert "Wrote" in out.content
    assert "wiki/routing-db.md" in out.content
    assert (tmp_path / "wiki" / "routing-db.md").is_file()
    log_text = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "wiki-archive" in log_text and "routing-db.md" in log_text
    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "[Routing discussion]" in index_text
    assert "PostgreSQL" in index_text

    assert len(sess.messages) == 1
    assert sess.messages[0]["role"] == "user"
    assert "wiki/index.md" in str(sess.messages[0]["content"])
    assert sess.last_consolidated == 0
    loop.sessions.save.assert_called_once_with(sess)
    loop.sessions.invalidate.assert_called_once_with(sess.key)


@pytest.mark.asyncio
async def test_cmd_wiki_archive_json_splits_two_topics(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    loop = MagicMock()
    _mock_loop_bus(loop)
    loop.consolidator.store = store
    loop.model = "test/model"

    payload = [
        {
            "category_slug": "auth-oauth",
            "display_title": "OAuth",
            "entry_markdown": "## Summary\n\nDevice flow.",
        },
        {
            "category_slug": "db-schema",
            "display_title": "Schema",
            "entry_markdown": "## Summary\n\nAdded users table.",
        },
    ]

    async def chat_with_retry(**kwargs):
        r = MagicMock()
        r.content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return r

    loop.provider.chat_with_retry = AsyncMock(side_effect=chat_with_retry)

    sess = Session(key="cli:t")
    sess.messages = [{"role": "user", "content": "hi", "timestamp": "2026-04-11T10:00:00"}]
    sess.last_consolidated = 0
    loop.sessions.get_or_create.return_value = sess
    loop.sessions.save = MagicMock()
    loop.sessions.invalidate = MagicMock()

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=sess, key="cli:t", raw="/wiki-archive", loop=loop)

    out = await cmd_wiki_archive(ctx)
    assert "2 topic(s)" in out.content
    assert (tmp_path / "wiki" / "auth-oauth.md").is_file()
    assert (tmp_path / "wiki" / "db-schema.md").is_file()


@pytest.mark.asyncio
async def test_cmd_wiki_archive_json_page_kind_routes_to_subdir(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    loop = MagicMock()
    _mock_loop_bus(loop)
    loop.consolidator.store = store
    loop.model = "test/model"

    payload = [
        {
            "category_slug": "acme-corp",
            "display_title": "Acme",
            "page_kind": "entity",
            "entry_markdown": "## Summary\n\nVendor for widgets.",
        },
        {
            "category_slug": "widget-pattern",
            "display_title": "Widget pattern",
            "page_kind": "concept",
            "entry_markdown": "## Summary\n\nFactory + adapter.",
        },
    ]

    async def chat_with_retry(**kwargs):
        r = MagicMock()
        r.content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return r

    loop.provider.chat_with_retry = AsyncMock(side_effect=chat_with_retry)

    sess = Session(key="cli:t")
    sess.messages = [{"role": "user", "content": "hi", "timestamp": "2026-04-11T10:00:00"}]
    sess.last_consolidated = 0
    loop.sessions.get_or_create.return_value = sess
    loop.sessions.save = MagicMock()
    loop.sessions.invalidate = MagicMock()

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=sess, key="cli:t", raw="/wiki-archive", loop=loop)

    out = await cmd_wiki_archive(ctx)
    assert "2 topic(s)" in out.content
    assert (tmp_path / "wiki" / "entities" / "acme-corp.md").is_file()
    assert (tmp_path / "wiki" / "concepts" / "widget-pattern.md").is_file()
    assert "wiki/entities/acme-corp.md" in out.content or "entities/acme-corp.md" in out.content

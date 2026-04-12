"""Tests for /wiki-lint, /wiki-save-answer, /wiki-ingest."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import MemoryStore
from nanobot.command.builtin import cmd_wiki_ingest, cmd_wiki_lint, cmd_wiki_save_answer
from nanobot.command.wiki_ingest import compute_wiki_ingest_bundle_sha256, run_wiki_ingest
from nanobot.command.router import CommandContext
from nanobot.session.manager import Session


@pytest.mark.asyncio
async def test_cmd_wiki_lint_reports_and_logs(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "x.md").write_text("Broken [[nope]] link.\n", encoding="utf-8")

    store = MemoryStore(tmp_path)
    loop = MagicMock()
    loop.consolidator.store = store

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=None, key="cli:t", raw="/wiki-lint", loop=loop)

    out = await cmd_wiki_lint(ctx)
    assert "Broken wikilink" in out.content or "dead" in out.content.lower()
    log = (wiki / "log.md").read_text(encoding="utf-8")
    assert "wiki-lint" in log


@pytest.mark.asyncio
async def test_cmd_wiki_save_answer_writes_queries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    loop = MagicMock()
    loop.consolidator.store = store
    loop.sessions.get_or_create = MagicMock()

    sess = Session(key="cli:t")
    sess.messages = [
        {"role": "user", "content": "q", "timestamp": "2026-04-11T10:00:00"},
        {"role": "assistant", "content": "The answer is 42.", "timestamp": "2026-04-11T10:00:01"},
    ]

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(
        msg=msg, session=sess, key="cli:t", raw="/wiki-save-answer my-answer", loop=loop,
        args="my-answer ",
    )
    # Prefix handler sets args — simulate exact match with slug via args
    ctx.args = "my-answer"

    out = await cmd_wiki_save_answer(ctx)
    assert "wiki/queries/my-answer.md" in out.content
    text = (tmp_path / "wiki" / "queries" / "my-answer.md").read_text(encoding="utf-8")
    assert "42" in text


@pytest.mark.asyncio
async def test_cmd_wiki_ingest_from_raw_sources(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "sources"
    raw.mkdir(parents=True)
    (raw / "note.md").write_text("# Note\n\nHello ingest world unique-xyz.\n", encoding="utf-8")

    store = MemoryStore(tmp_path)
    loop = MagicMock()
    loop.consolidator.store = store
    loop.model = "test/model"

    payload = [
        {
            "category_slug": "ingest-note",
            "display_title": "Note",
            "page_kind": "topic",
            "entry_markdown": "## Summary\n\nunique-xyz captured.",
        },
    ]

    async def chat_with_retry(**kwargs):
        r = MagicMock()
        r.content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return r

    loop.provider.chat_with_retry = AsyncMock(side_effect=chat_with_retry)

    msg = MagicMock(channel="cli", chat_id="t", session_key="cli:t", metadata={})
    ctx = CommandContext(msg=msg, session=None, key="cli:t", raw="/wiki-ingest", loop=loop)

    out = await cmd_wiki_ingest(ctx)
    assert "ingest-note.md" in out.content or "wiki/" in out.content
    assert (tmp_path / "wiki" / "ingest-note.md").is_file()
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "wiki-ingest" in log


@pytest.mark.asyncio
async def test_run_wiki_ingest_skips_model_when_raw_bundle_unchanged(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "sources"
    raw.mkdir(parents=True)
    (raw / "n.md").write_text("hello bundle", encoding="utf-8")

    paths = ["raw/sources/n.md"]
    bundle_sha = compute_wiki_ingest_bundle_sha256(tmp_path, paths)
    (tmp_path / "memory").mkdir(exist_ok=True)
    (tmp_path / "memory" / "wiki_ingest_state.json").write_text(
        json.dumps({"last_success_bundle_sha256": bundle_sha, "body_sha256": []}),
        encoding="utf-8",
    )

    store = MemoryStore(tmp_path)
    loop = MagicMock()
    loop.consolidator.store = store
    loop.model = "x"
    chat = AsyncMock()
    loop.provider.chat_with_retry = chat

    result = await run_wiki_ingest(loop, workspace=tmp_path)
    assert result.ok
    assert not result.called_model
    chat.assert_not_called()


@pytest.mark.asyncio
async def test_run_wiki_ingest_force_bypasses_bundle_skip(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "sources"
    raw.mkdir(parents=True)
    (raw / "n.md").write_text("hello bundle", encoding="utf-8")

    paths = ["raw/sources/n.md"]
    bundle_sha = compute_wiki_ingest_bundle_sha256(tmp_path, paths)
    (tmp_path / "memory").mkdir(exist_ok=True)
    (tmp_path / "memory" / "wiki_ingest_state.json").write_text(
        json.dumps({"last_success_bundle_sha256": bundle_sha, "body_sha256": []}),
        encoding="utf-8",
    )

    store = MemoryStore(tmp_path)
    loop = MagicMock()
    loop.consolidator.store = store
    loop.model = "x"
    payload = [
        {
            "category_slug": "force-ingest",
            "display_title": "Force",
            "page_kind": "topic",
            "entry_markdown": "## Summary\n\nforced run unique.",
        },
    ]

    async def chat_with_retry(**kwargs):
        r = MagicMock()
        r.content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return r

    loop.provider.chat_with_retry = AsyncMock(side_effect=chat_with_retry)

    result = await run_wiki_ingest(loop, workspace=tmp_path, force_refresh=True)
    assert result.called_model
    assert result.ok
    assert (tmp_path / "wiki" / "force-ingest.md").is_file()

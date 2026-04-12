"""Tests for multi-page wiki context in MemoryStore."""

import json
from pathlib import Path

import pytest

from nanobot.agent.memory import MemoryStore
from nanobot.llm_wiki import (
    STANDARD_WIKI_SUBDIRS,
    build_wiki_context,
    list_wiki_page_paths,
    read_schema,
)


def test_merge_wiki_entries_from_archive_writes_index(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    when = "2026-04-11 12:00"
    entries = [
        ("alpha-topic", "Alpha", "## Summary\n\nOne.", "topic"),
        ("beta-corp", "Beta", "## Summary\n\nTwo.", "entity"),
    ]
    out = store.merge_wiki_entries_from_archive(entries, when)
    assert "alpha-topic.md" in out
    assert "entities/beta-corp.md" in out
    assert (tmp_path / "wiki" / "alpha-topic.md").is_file()
    assert (tmp_path / "wiki" / "entities" / "beta-corp.md").is_file()
    idx = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "Alpha" in idx and "Beta" in idx


def test_coalesce_wiki_archive_entries_merges_same_slug_in_batch() -> None:
    entries = [
        ("dup", "D", "## Summary\n\nOne", "topic"),
        ("dup", "D", "## Summary\n\nTwo", "topic"),
    ]
    out = MemoryStore.coalesce_wiki_archive_entries(entries)
    assert len(out) == 1
    assert out[0][0] == "dup"
    assert "One" in out[0][2] and "Two" in out[0][2]


def test_merge_wiki_entries_single_index_line_for_batch_duplicate_slug(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    when = "2026-04-11 12:00"
    entries = [
        ("dup-topic", "Dup", "## Summary\n\nOne", "topic"),
        ("dup-topic", "Dup", "## Summary\n\nTwo", "topic"),
    ]
    store.merge_wiki_entries_from_archive(entries, when)
    idx = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert idx.count("dup-topic.md") == 1


def test_remap_wiki_slug_to_existing_h1(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.wiki_dir.mkdir(parents=True)
    (store.wiki_dir / "concepts").mkdir(parents=True)
    (store.wiki_dir / "concepts" / "tensorflow.md").write_text(
        "# TensorFlow\n\n> notes\n",
        encoding="utf-8",
    )
    when = "2026-04-11 12:00"
    entries = [
        ("tensorflow-alt-slug", "TensorFlow", "## Summary\n\nExtra.", "concept"),
    ]
    store.merge_wiki_entries_from_archive(entries, when)
    assert not (store.wiki_dir / "concepts" / "tensorflow-alt-slug.md").is_file()
    text = (store.wiki_dir / "concepts" / "tensorflow.md").read_text(encoding="utf-8")
    assert "Extra." in text


def test_append_wiki_log_line_creates_file(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.append_wiki_log_line("test-kind", "short summary", when="2026-01-01 00:00")
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "test-kind" in log and "short summary" in log


def test_memory_store_wiki_delegates_to_llm_wiki(tmp_path: Path) -> None:
    """MemoryStore wiki helpers must stay thin wrappers around :mod:`nanobot.llm_wiki`."""
    ws = tmp_path / "ws"
    (ws / "wiki").mkdir(parents=True)
    (ws / "wiki" / "schema.md").write_text("schema line\n", encoding="utf-8")
    (ws / "wiki" / "index.md").write_text("index\n", encoding="utf-8")
    (ws / "wiki" / "z.md").write_text("z\n", encoding="utf-8")

    store = MemoryStore(ws)
    assert store.list_wiki_page_paths() == list_wiki_page_paths(ws, wiki_dir=store.WIKI_DIR)
    assert store.read_wiki_schema() == read_schema(ws, wiki_dir=store.WIKI_DIR)
    for budget in (200, 800, 4000):
        assert store.get_wiki_context(max_total_chars=budget) == build_wiki_context(
            ws, wiki_dir=store.WIKI_DIR, max_total_chars=budget,
        )


def test_append_session_archive_to_index_creates_section(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.append_session_archive_to_index(
        "context-test.md",
        "2026-04-11 12:00",
        title="Auth notes",
        blurb="OAuth migration and callback URLs.",
    )
    for name in STANDARD_WIKI_SUBDIRS:
        assert (tmp_path / "wiki" / name).is_dir()
    idx = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "Topic archives" in idx
    assert "context-test.md" in idx
    assert "[Auth notes]" in idx
    assert "OAuth migration" in idx


def test_is_wiki_archive_body_insufficient() -> None:
    assert MemoryStore.is_wiki_archive_body_insufficient("")
    assert MemoryStore.is_wiki_archive_body_insufficient("   ")
    assert MemoryStore.is_wiki_archive_body_insufficient("# (empty session)\n")
    assert MemoryStore.is_wiki_archive_body_insufficient(
        "CATEGORY_SLUG: empty-session\n\n# (empty session)\n",
    )
    assert MemoryStore.is_wiki_archive_body_insufficient("No heading but text")
    assert not MemoryStore.is_wiki_archive_body_insufficient(
        "CATEGORY_SLUG: foo\nDISPLAY_TITLE: Bar\n\n## Summary\n\nHello.\n",
    )


def test_parse_wiki_archive_entries_json_multi() -> None:
    payload = [
        {"category_slug": "a", "display_title": "A", "entry_markdown": "## Summary\n\none"},
        {"category_slug": "b", "display_title": "B", "page_kind": "concept", "entry_markdown": "## Summary\n\ntwo"},
    ]
    raw = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    entries = MemoryStore.parse_wiki_archive_entries(raw)
    assert len(entries) == 2
    assert entries[0][:4] == ("a", "A", "## Summary\n\none", "topic")
    assert entries[1][:4] == ("b", "B", "## Summary\n\ntwo", "concept")


def test_merge_wiki_category_document_respects_page_kind(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.merge_wiki_category_document(
        "acme", "Acme", "## Summary\n\nx", "2026-04-11 10:00", page_kind="entity",
    )
    assert (tmp_path / "wiki" / "entities" / "acme.md").is_file()
    store.merge_wiki_category_document(
        "oauth", "OAuth", "## Summary\n\ny", "2026-04-11 11:00", page_kind="concept",
    )
    assert (tmp_path / "wiki" / "concepts" / "oauth.md").is_file()
    store.merge_wiki_category_document(
        "pg-vs-mysql", "Postgres vs MySQL", "## Summary\n\nz", "2026-04-11 12:00", page_kind="comparison",
    )
    assert (tmp_path / "wiki" / "comparisons" / "pg-vs-mysql.md").is_file()


def test_merge_wiki_category_document_appends_same_file(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.merge_wiki_category_document("alpha", "Alpha", "## Summary\n\nFirst.", "2026-04-11 10:00", page_kind="topic")
    store.merge_wiki_category_document("alpha", "Alpha", "## Summary\n\nSecond.", "2026-04-11 11:00", page_kind="topic")
    text = (tmp_path / "wiki" / "alpha.md").read_text(encoding="utf-8")
    assert "First." in text and "Second." in text
    assert text.count("## 2026-04-11") == 2


def test_summarize_wiki_archive_for_index_prefers_summary_section(tmp_path: Path) -> None:
    body = """# Project Alpha

## Summary

First production deploy succeeded. Monitoring enabled.

## Details

- Rollout plan
"""
    title, blurb = MemoryStore.summarize_wiki_archive_for_index(body)
    assert title == "Project Alpha"
    assert "production deploy" in blurb.lower()
    assert "Monitoring" in blurb


def test_write_wiki_page_rejects_traversal(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    with pytest.raises(ValueError):
        store.write_wiki_page("../evil.md", "x")

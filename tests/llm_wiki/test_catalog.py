"""Tests for wiki page catalog helper."""

from pathlib import Path

from nanobot.llm_wiki.catalog import build_wiki_existing_pages_catalog, extract_markdown_h1


def test_extract_markdown_h1() -> None:
    assert extract_markdown_h1("# Hello\n\nx") == "Hello"
    assert extract_markdown_h1("no heading") == ""


def test_build_wiki_existing_pages_catalog_skips_special_pages(tmp_path: Path) -> None:
    w = tmp_path / "wiki"
    w.mkdir()
    (w / "index.md").write_text("# Index\n", encoding="utf-8")
    (w / "schema.md").write_text("# Schema\n", encoding="utf-8")
    (w / "note.md").write_text("# My Note\n\nx\n", encoding="utf-8")
    cat = build_wiki_existing_pages_catalog(tmp_path, max_chars=4000)
    assert "index.md" not in cat
    assert "note.md" in cat
    assert "My Note" in cat

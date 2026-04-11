"""Unit tests for :mod:`nanobot.llm_wiki` (no MemoryStore)."""

from pathlib import Path

from nanobot.llm_wiki import (
    STANDARD_WIKI_SUBDIRS,
    build_wiki_context,
    ensure_standard_wiki_dirs,
    list_wiki_page_paths,
    read_schema,
    wiki_schema_rel,
)


def test_wiki_schema_rel_default() -> None:
    assert wiki_schema_rel() == "wiki/schema.md"


def test_ensure_standard_wiki_dirs_creates_layout(tmp_path: Path) -> None:
    ensure_standard_wiki_dirs(tmp_path)
    for name in STANDARD_WIKI_SUBDIRS:
        assert (tmp_path / "wiki" / name).is_dir()
    ensure_standard_wiki_dirs(tmp_path)  # idempotent
    assert (tmp_path / "wiki" / "entities").is_dir()


def test_list_wiki_page_paths_orders_index_first(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "wiki" / "zebra.md").write_text("z", encoding="utf-8")
    (tmp_path / "wiki" / "index.md").write_text("i", encoding="utf-8")
    (tmp_path / "wiki" / "sub").mkdir()
    (tmp_path / "wiki" / "sub" / "a.md").write_text("a", encoding="utf-8")

    paths = list_wiki_page_paths(tmp_path)
    assert paths[0].endswith("wiki/index.md")
    assert "wiki/sub/a.md" in paths
    assert "wiki/zebra.md" in paths


def test_build_wiki_context_prepends_schema_before_other_pages(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "wiki" / "schema.md").write_text(
        "SCHEMA-RULE: prefer wikilinks.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "index.md").write_text("y" * 8000, encoding="utf-8")

    out = build_wiki_context(tmp_path, max_total_chars=600)
    assert "SCHEMA-RULE" in out
    assert "wiki/schema.md" in out
    assert out.find("SCHEMA-RULE") < out.find("wiki/index.md")
    assert out.count("wiki/schema.md") == 1


def test_read_schema_empty_when_missing(tmp_path: Path) -> None:
    assert read_schema(tmp_path / "ws") == ""


def test_build_wiki_context_truncates_by_budget(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "wiki" / "index.md").write_text("x" * 500, encoding="utf-8")

    out = build_wiki_context(tmp_path, max_total_chars=120)
    assert "wiki/index.md" in out
    assert "truncated" in out.lower()


def test_build_wiki_context_empty_when_no_wiki(tmp_path: Path) -> None:
    assert build_wiki_context(tmp_path / "ws") == ""


def test_custom_wiki_dir_name(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir(parents=True)
    (tmp_path / "notes" / "index.md").write_text("hi", encoding="utf-8")
    out = build_wiki_context(tmp_path, wiki_dir="notes", max_total_chars=500)
    assert "notes/index.md" in out
    assert read_schema(tmp_path, wiki_dir="notes") == ""
    assert wiki_schema_rel(wiki_dir="notes") == "notes/schema.md"

"""Tests for nanobot.llm_wiki.lint."""

from pathlib import Path

from nanobot.llm_wiki.lint import run_wiki_lint


def test_run_wiki_lint_dead_link(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text("See [[missing-page]] for details.\n", encoding="utf-8")
    r = run_wiki_lint(tmp_path)
    assert len(r.dead_links) == 1
    assert r.dead_links[0][1] == "missing-page"


def test_run_wiki_lint_resolves_entity_page(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    (wiki / "entities" / "acme.md").write_text("ok\n", encoding="utf-8")
    (wiki / "b.md").write_text("Link [[acme]] here.\n", encoding="utf-8")
    r = run_wiki_lint(tmp_path)
    assert r.dead_links == []


def test_run_wiki_lint_orphan(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    (wiki / "entities" / "lonely.md").write_text("no links in\n", encoding="utf-8")
    (wiki / "index.md").write_text("# Index\n", encoding="utf-8")
    r = run_wiki_lint(tmp_path)
    orphan_rels = [p for p in r.orphan_pages if "lonely" in p]
    assert len(orphan_rels) == 1

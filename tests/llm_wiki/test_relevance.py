"""Tests for relevance-ranked wiki context."""

from pathlib import Path

from nanobot.llm_wiki import build_wiki_context


def test_build_wiki_context_relevance_orders_matching_page_first(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "zebra.md").write_text("# Z\n\napple banana discussion.\n", encoding="utf-8")
    (wiki / "match.md").write_text("# M\n\nuniquekeyword-xyz rare token here.\n", encoding="utf-8")

    out_default = build_wiki_context(tmp_path, max_total_chars=8000)
    out_ranked = build_wiki_context(
        tmp_path,
        max_total_chars=8000,
        relevance_query="uniquekeyword-xyz",
    )
    assert "uniquekeyword-xyz" in out_ranked
    pos_match = out_ranked.find("wiki/match.md")
    pos_zebra = out_ranked.find("wiki/zebra.md")
    assert pos_match < pos_zebra
    assert out_default  # alphabetical / default path order still includes both files

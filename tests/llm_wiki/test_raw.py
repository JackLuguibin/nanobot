"""Tests for nanobot.llm_wiki.raw."""

from pathlib import Path

from nanobot.llm_wiki.raw import ensure_raw_directories, list_raw_source_files


def test_ensure_raw_directories(tmp_path: Path) -> None:
    ensure_raw_directories(tmp_path)
    assert (tmp_path / "raw" / "sources").is_dir()
    assert (tmp_path / "raw" / "articles").is_dir()
    assert (tmp_path / "raw" / "papers").is_dir()
    assert (tmp_path / "raw" / "transcripts").is_dir()
    assert (tmp_path / "raw" / "assets").is_dir()


def test_list_raw_source_files_sorted(tmp_path: Path) -> None:
    ensure_raw_directories(tmp_path)
    (tmp_path / "raw" / "sources" / "z.md").write_text("z", encoding="utf-8")
    (tmp_path / "raw" / "sources" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "raw" / "articles" / "clip.md").write_text("c", encoding="utf-8")
    paths = list_raw_source_files(tmp_path)
    assert paths == [
        "raw/articles/clip.md",
        "raw/sources/a.txt",
        "raw/sources/z.md",
    ]

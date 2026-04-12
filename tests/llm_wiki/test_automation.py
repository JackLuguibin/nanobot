"""Tests for wiki automation fingerprints and state."""

from pathlib import Path

from nanobot.llm_wiki.automation import compute_raw_fingerprint, wiki_automation_state_path
from nanobot.llm_wiki.raw import ensure_raw_directories


def test_compute_raw_fingerprint_changes_with_mtime(tmp_path: Path) -> None:
    ensure_raw_directories(tmp_path)
    p = tmp_path / "raw" / "sources" / "a.md"
    p.write_text("v1", encoding="utf-8")
    fp1 = compute_raw_fingerprint(tmp_path)
    p.write_text("v2", encoding="utf-8")
    fp2 = compute_raw_fingerprint(tmp_path)
    assert fp1 != fp2


def test_wiki_automation_state_under_memory(tmp_path: Path) -> None:
    assert wiki_automation_state_path(tmp_path) == tmp_path / "memory" / "wiki_automation.json"

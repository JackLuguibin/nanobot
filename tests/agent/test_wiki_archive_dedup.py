"""Tests for /wiki-archive duplicate detection (MemoryStore)."""

from pathlib import Path

from nanobot.agent.memory import MemoryStore


def test_wiki_archive_transcript_dedup_roundtrip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    h = "deadbeef" * 8  # 64 hex-like id
    assert not store.wiki_archive_transcript_already_archived(h)
    store.wiki_archive_remember_success(h, "# Page\n\n## Summary\n\nUnique content here.")
    assert store.wiki_archive_transcript_already_archived(h)
    p = tmp_path / "memory" / "wiki_archive_dedup.json"
    assert p.is_file()


def test_wiki_archive_skips_same_body_hash(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    body = "# Same\n\n## Summary\n\nIdentical archive text."
    store.wiki_archive_remember_success("transcript_hash_aaa", body)
    assert store.wiki_archive_should_skip_duplicate_body(body)


def test_wiki_archive_near_duplicate_file(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    (store.wiki_dir).mkdir(parents=True)
    slight = "# Topic\n\n## Summary\n\nHello world and more text for length."
    (store.wiki_dir / "legacy-topic.md").write_text(slight, encoding="utf-8")
    # Almost the same normalized text -> high ratio
    body = "# Topic\n\n## Summary\n\nHello world and more text for length!"
    assert store.wiki_archive_should_skip_duplicate_body(body, similarity_threshold=0.90)

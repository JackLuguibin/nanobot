"""Immutable raw sources layer (Karpathy llm-wiki): layered ``raw/`` + ``raw/assets``."""

from __future__ import annotations

from pathlib import Path

RAW_DIR_NAME = "raw"
RAW_SOURCES_REL = f"{RAW_DIR_NAME}/sources"
RAW_ARTICLES_REL = f"{RAW_DIR_NAME}/articles"
RAW_PAPERS_REL = f"{RAW_DIR_NAME}/papers"
RAW_TRANSCRIPTS_REL = f"{RAW_DIR_NAME}/transcripts"
RAW_ASSETS_REL = f"{RAW_DIR_NAME}/assets"
# Roots scanned for text ingest (articles, papers, transcripts, legacy flat ``sources``).
RAW_TEXT_SOURCE_RELS: tuple[str, ...] = (
    RAW_SOURCES_REL,
    RAW_ARTICLES_REL,
    RAW_PAPERS_REL,
    RAW_TRANSCRIPTS_REL,
)
# Text-like sources ingest reads; binary formats require separate tooling.
RAW_SOURCE_TEXT_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".txt", ".rst"})


def ensure_raw_directories(workspace: Path) -> None:
    """Create ``raw/sources``, ``raw/articles``, ``raw/papers``, ``raw/transcripts``, ``raw/assets``."""
    for rel in RAW_TEXT_SOURCE_RELS:
        (workspace / rel).mkdir(parents=True, exist_ok=True)
    (workspace / RAW_ASSETS_REL).mkdir(parents=True, exist_ok=True)


def _collect_text_files_under(workspace: Path, root_rel: str, ext: frozenset[str]) -> list[str]:
    root = workspace / root_rel
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf not in ext:
            continue
        out.append(str(p.relative_to(workspace)).replace("\\", "/"))
    return out


def list_raw_source_files(
    workspace: Path,
    *,
    extensions: frozenset[str] | None = None,
) -> list[str]:
    """Sorted relative posix paths under all text source roots (see ``RAW_TEXT_SOURCE_RELS``).

    Only includes files whose suffix matches *extensions* (default: text-like).
    Does not read file contents.
    """
    ext = extensions if extensions is not None else RAW_SOURCE_TEXT_EXTENSIONS
    seen: set[str] = set()
    ordered: list[str] = []
    for rel in RAW_TEXT_SOURCE_RELS:
        for p in _collect_text_files_under(workspace, rel, ext):
            if p not in seen:
                seen.add(p)
                ordered.append(p)
    ordered.sort()
    return ordered

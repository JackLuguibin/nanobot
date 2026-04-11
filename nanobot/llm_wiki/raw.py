"""Immutable raw sources layer (Karpathy llm-wiki): ``raw/sources``, ``raw/assets``."""

from __future__ import annotations

from pathlib import Path

RAW_DIR_NAME = "raw"
RAW_SOURCES_REL = f"{RAW_DIR_NAME}/sources"
RAW_ASSETS_REL = f"{RAW_DIR_NAME}/assets"
# Text-like sources ingest reads; binary formats require separate tooling.
RAW_SOURCE_TEXT_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".txt", ".rst"})


def ensure_raw_directories(workspace: Path) -> None:
    """Create ``raw/sources`` and ``raw/assets`` if missing."""
    (workspace / RAW_SOURCES_REL).mkdir(parents=True, exist_ok=True)
    (workspace / RAW_ASSETS_REL).mkdir(parents=True, exist_ok=True)


def list_raw_source_files(
    workspace: Path,
    *,
    extensions: frozenset[str] | None = None,
) -> list[str]:
    """Sorted relative posix paths under ``raw/sources/`` (files only).

    Only includes files whose suffix matches *extensions* (default: text-like).
    Does not read file contents.
    """
    ext = extensions if extensions is not None else RAW_SOURCE_TEXT_EXTENSIONS
    root = workspace / RAW_SOURCES_REL
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
    return sorted(out)

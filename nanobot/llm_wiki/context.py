"""LLM Wiki filesystem layout: schema-first context assembly for prompt injection.

Implements the Karpathy-style convention: optional ``wiki/schema.md`` defines
structure; standard subdirs ``entities/``, ``concepts/``, ``sources/`` hold typed
pages; other markdown may live at ``wiki/`` root. ``index.md`` is the catalog entry.
This module is intentionally free of MemoryStore / agent / channel imports.
"""

from __future__ import annotations

import re
from pathlib import Path

WIKI_DIR_NAME = "wiki"
SCHEMA_FILENAME = "schema.md"
# Karpathy / llm-wiki style layout: typed pages under these subdirectories.
STANDARD_WIKI_SUBDIRS: tuple[str, ...] = ("entities", "concepts", "sources")
DEFAULT_MAX_TOTAL_CHARS = 24_000
DEFAULT_SCHEMA_CONTEXT_CAP = 12_000


def wiki_schema_rel(*, wiki_dir: str = WIKI_DIR_NAME) -> str:
    """Relative posix path ``wiki/schema.md`` (or ``<wiki_dir>/schema.md``)."""
    return f"{wiki_dir}/{SCHEMA_FILENAME}"


def ensure_standard_wiki_dirs(workspace: Path, *, wiki_dir: str = WIKI_DIR_NAME) -> None:
    """Create ``wiki/entities``, ``wiki/concepts``, ``wiki/sources`` if missing."""
    base = workspace / wiki_dir
    for name in STANDARD_WIKI_SUBDIRS:
        (base / name).mkdir(parents=True, exist_ok=True)


def read_schema(workspace: Path, *, wiki_dir: str = WIKI_DIR_NAME) -> str:
    """Return ``wiki/schema.md`` text, or empty string if missing or unreadable."""
    p = workspace / wiki_dir / SCHEMA_FILENAME
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def list_wiki_page_paths(workspace: Path, *, wiki_dir: str = WIKI_DIR_NAME) -> list[str]:
    """Sorted relative paths ``wiki/**/*.md`` (posix). ``wiki/index.md`` first if present."""
    root = workspace / wiki_dir
    if not root.is_dir():
        return []
    paths = [
        str(p.relative_to(workspace)).replace("\\", "/")
        for p in root.rglob("*.md")
    ]
    paths.sort()
    idx_key = f"{wiki_dir}/index.md"
    if idx_key in paths:
        paths.remove(idx_key)
        paths.insert(0, idx_key)
    return paths


def _tokenize_for_relevance(text: str) -> set[str]:
    return {x.lower() for x in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text) if len(x) >= 2}


def _score_wiki_page(rel: str, body: str, query_tokens: set[str]) -> int:
    if not query_tokens:
        return 0
    hay = (rel + "\n" + body[:12000]).lower()
    return sum(2 for t in query_tokens if t in hay)


def build_wiki_context(
    workspace: Path,
    *,
    wiki_dir: str = WIKI_DIR_NAME,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    schema_context_cap: int = DEFAULT_SCHEMA_CONTEXT_CAP,
    relevance_query: str | None = None,
) -> str:
    """Concatenate wiki markdown for system prompt injection (token-bounded).

    When ``wiki/schema.md`` exists, it is injected **first** (up to *schema_context_cap*)
    so structural rules are not dropped when ``index.md`` or topic files consume the
    budget. Remaining pages follow :func:`list_wiki_page_paths` order, excluding the
    schema file to avoid duplication.

    When *relevance_query* is set, non-schema pages are ordered by simple token overlap
    with the query (title + body prefix) so the most relevant pages survive truncation.
    """
    parts: list[str] = []
    remaining = max_total_chars
    schema_rel = wiki_schema_rel(wiki_dir=wiki_dir)
    schema_path = workspace / wiki_dir / SCHEMA_FILENAME
    query_tokens = _tokenize_for_relevance(relevance_query) if relevance_query else set()
    if schema_path.is_file():
        try:
            body = schema_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        if body.strip():
            header = f"## {schema_rel}\n\n"
            cap = min(schema_context_cap, max(0, remaining - len(header)))
            if cap >= 40:
                chunk = body
                if len(chunk) > cap:
                    chunk = chunk[: max(0, cap - 40)].rstrip() + "\n\n… *(truncated)*"
                block = header + chunk
                parts.append(block)
                remaining -= len(block)

    page_paths = [p for p in list_wiki_page_paths(workspace, wiki_dir=wiki_dir) if p != schema_rel]
    if query_tokens:
        scored: list[tuple[int, str, str]] = []
        for rel in page_paths:
            path = workspace / rel
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            sc = _score_wiki_page(rel, body, query_tokens)
            scored.append((sc, rel, body))
        scored.sort(key=lambda x: (-x[0], x[1]))
        ordered = [(rel, body) for _, rel, body in scored]
    else:
        ordered = []
        for rel in page_paths:
            path = workspace / rel
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ordered.append((rel, body))

    for rel, body in ordered:
        header = f"## {rel}\n\n"
        if remaining <= len(header) + 20:
            break
        budget = remaining - len(header)
        chunk = body
        if len(chunk) > budget:
            chunk = chunk[: max(0, budget - 40)].rstrip() + "\n\n… *(truncated)*"
        block = header + chunk
        parts.append(block)
        remaining -= len(block)
        if remaining < 100:
            break
    return "\n\n".join(parts).strip()

"""Compact listing of existing wiki pages for ingest/archive prompts."""

from __future__ import annotations

import re
from pathlib import Path

from nanobot.llm_wiki.context import WIKI_DIR_NAME, list_wiki_page_paths

_SKIP_NAMES = frozenset(
    {
        "index.md",
        "schema.md",
        "log.md",
    },
)


def extract_markdown_h1(text: str) -> str:
    """First markdown H1 heading text, or empty."""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^#\s+(.+)$", s)
        if m:
            return m.group(1).strip()
    return ""


def build_wiki_existing_pages_catalog(
    workspace: Path,
    *,
    wiki_dir: str = WIKI_DIR_NAME,
    max_chars: int = 6000,
    per_file_read_cap: int = 8192,
) -> str:
    """Human-readable lines ``relative_path — H1`` for prompt injection (capped)."""
    paths = list_wiki_page_paths(workspace, wiki_dir=wiki_dir)
    lines: list[str] = []
    total = 0
    prefix = f"{wiki_dir}/"
    for rel in paths:
        if not rel.startswith(prefix):
            continue
        tail = rel[len(prefix) :]
        if tail in _SKIP_NAMES or tail.startswith("queries/"):
            continue
        p = workspace / rel
        try:
            chunk = p.read_text(encoding="utf-8", errors="replace")[:per_file_read_cap]
        except OSError:
            continue
        h1 = extract_markdown_h1(chunk)
        label = h1 if h1 else "(no H1)"
        line = f"- `{tail}` — {label}"
        if total + len(line) + 1 > max_chars:
            lines.append("… *(catalog truncated)*")
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return "(No wiki pages yet besides index/schema.)"
    return "\n".join(lines)

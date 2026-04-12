"""Lightweight wiki lint: wikilink targets and optional orphan pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from nanobot.llm_wiki.context import WIKI_DIR_NAME

# [[Page]] or [[Page|label]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _slug_from_link_text(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "page"


def _wiki_page_paths(workspace: Path, wiki_dir: str) -> set[str]:
    """Paths relative to *wiki_dir*: ``foo.md``, ``entities/bar.md``."""
    root = workspace / wiki_dir
    if not root.is_dir():
        return set()
    out: set[str] = set()
    for p in root.rglob("*.md"):
        rel = p.relative_to(root).as_posix()
        if rel in ("index.md", "log.md", "schema.md"):
            continue
        if rel.endswith("/README.md") or rel == "README.md":
            continue
        out.add(rel)
    return out


def _resolve_wikilink_to_page(slug: str, wiki_paths: set[str]) -> str | None:
    """Return wiki-relative path if *slug* matches an existing page."""
    candidates = (
        f"{slug}.md",
        f"entities/{slug}.md",
        f"concepts/{slug}.md",
        f"sources/{slug}.md",
        f"comparisons/{slug}.md",
        f"queries/{slug}.md",
    )
    for c in candidates:
        if c in wiki_paths:
            return c
    for p in wiki_paths:
        stem = Path(p).stem.lower().replace(" ", "-")
        if stem == slug:
            return p
    return None


@dataclass
class WikiLintReport:
    dead_links: list[tuple[str, str]] = field(default_factory=list)  # (workspace_rel, link_text)
    orphan_pages: list[str] = field(default_factory=list)  # workspace-relative wiki paths


def run_wiki_lint(workspace: Path, *, wiki_dir: str = WIKI_DIR_NAME) -> WikiLintReport:
    """Scan ``wiki/**/*.md`` for broken ``[[wikilinks]]`` and pages with no inbound wikilinks."""
    wiki_root = workspace / wiki_dir
    report = WikiLintReport()
    if not wiki_root.is_dir():
        return report

    wiki_paths = _wiki_page_paths(workspace, wiki_dir)
    inbound: dict[str, set[str]] = {p: set() for p in wiki_paths}

    for p in wiki_root.rglob("*.md"):
        rel_wiki = p.relative_to(wiki_root).as_posix()
        rel_ws = str(p.relative_to(workspace)).replace("\\", "/")
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _WIKILINK_RE.finditer(text):
            raw = m.group(1).strip()
            slug = _slug_from_link_text(raw)
            target = _resolve_wikilink_to_page(slug, wiki_paths)
            if target is None:
                report.dead_links.append((rel_ws, raw))
            else:
                inbound.setdefault(target, set()).add(rel_wiki)

    for rel, srcs in inbound.items():
        if srcs:
            continue
        full = f"{wiki_dir}/{rel}".replace("\\", "/")
        report.orphan_pages.append(full)

    report.orphan_pages.sort()
    return report


def format_wiki_lint_message(report: WikiLintReport, *, max_lines: int = 30) -> str:
    """Human-readable summary for channels."""
    lines: list[str] = []
    if report.dead_links:
        lines.append(f"Broken wikilinks ({len(report.dead_links)}):")
        for f, link in report.dead_links[:max_lines]:
            lines.append(f"  - {f}: [[{link}]]")
        if len(report.dead_links) > max_lines:
            lines.append(f"  … and {len(report.dead_links) - max_lines} more")
    if report.orphan_pages:
        lines.append(f"Orphan pages (no inbound [[wikilink]], {len(report.orphan_pages)}):")
        for p in report.orphan_pages[:max_lines]:
            lines.append(f"  - {p}")
        if len(report.orphan_pages) > max_lines:
            lines.append(f"  … and {len(report.orphan_pages) - max_lines} more")
    if not lines:
        return "Wiki lint: no broken wikilinks; no orphan pages detected (or wiki empty)."
    return "\n".join(lines)

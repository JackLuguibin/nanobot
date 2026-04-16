"""Shared wiki-ingest execution (manual `/wiki-ingest` and scheduled automation)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from nanobot.agent.memory import MemoryStore
from nanobot.llm_wiki import read_schema
from nanobot.llm_wiki.catalog import build_wiki_existing_pages_catalog
from nanobot.utils.helpers import strip_think
from nanobot.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


@dataclass
class WikiIngestResult:
    """Outcome of a wiki-ingest run (model may be skipped when there is nothing to read)."""

    ok: bool
    message: str
    written_paths: list[str]
    called_model: bool


def compute_wiki_ingest_bundle_sha256(workspace: Path, rel_paths: list[str]) -> str:
    """Stable hash of sorted ``path\\tsha256(content)`` lines for selected raw files."""
    lines: list[str] = []
    for rel in sorted(rel_paths):
        p = workspace / rel
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            digest = hashlib.sha256(b"").hexdigest()
        lines.append(f"{rel}\t{digest}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


async def run_wiki_ingest(
    loop: AgentLoop,
    *,
    workspace: Path,
    path_filter: str = "",
    force_refresh: bool = False,
) -> WikiIngestResult:
    """Read text from ``raw/`` roots, call the model, merge into ``wiki/``.

    *path_filter* — if non-empty, only include source paths whose relative path contains
    this substring (case-insensitive).

    *force_refresh* — when false (default), skip the model call if the raw bundle matches
    the last successful ingest; use true to always run (e.g. ``/wiki-ingest force``).
    """
    from nanobot.llm_wiki.raw import ensure_raw_directories, list_raw_source_files

    store = loop.consolidator.store
    ensure_raw_directories(workspace)
    paths = list_raw_source_files(workspace)
    pf = path_filter.strip()
    if pf:
        paths = [p for p in paths if pf.lower() in p.lower()]
    if not paths:
        return WikiIngestResult(
            ok=True,
            message="no raw text files to ingest",
            written_paths=[],
            called_model=False,
        )

    max_files, max_chars = 12, 100_000
    bundle_paths = paths[:max_files]
    bundle_sha = compute_wiki_ingest_bundle_sha256(workspace, bundle_paths)
    if not force_refresh and store.wiki_ingest_bundle_matches_last_success(bundle_sha):
        return WikiIngestResult(
            ok=True,
            message=(
                "wiki-ingest: raw bundle unchanged since last successful ingest; skipped. "
                "Use `/wiki-ingest force` to run anyway."
            ),
            written_paths=[],
            called_model=False,
        )

    chunks: list[str] = []
    for rel in bundle_paths:
        p = workspace / rel
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            chunks.append(f"## {rel}\n\n*(unreadable: {e})*")
            continue
        if len(body) > max_chars:
            body = body[:max_chars] + "\n\n… *(truncated)*\n"
        chunks.append(f"## {rel}\n\n{body}")
    bundle = "\n\n---\n\n".join(chunks)

    wiki_schema = read_schema(workspace).strip()
    wiki_catalog = build_wiki_existing_pages_catalog(workspace, max_chars=6000)
    try:
        response = await loop.provider.chat_with_retry(
            model=loop.model,
            messages=[
                {
                    "role": "system",
                    "content": render_template(
                        "agent/wiki_ingest.md",
                        strip=True,
                        wiki_schema=wiki_schema,
                        wiki_catalog=wiki_catalog,
                    ),
                },
                {"role": "user", "content": f"## Raw files\n\n{bundle}"},
            ],
            tools=None,
            tool_choice=None,
        )
    except Exception as e:
        return WikiIngestResult(
            ok=False,
            message=f"wiki-ingest: model call failed: {e}",
            written_paths=[],
            called_model=True,
        )

    body = strip_think(response.content or "").strip()
    if body.startswith("```"):
        lines = body.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()

    if store.wiki_ingest_should_skip_duplicate_body(body):
        store.wiki_ingest_remember_duplicate_body_skip(bundle_sha, body)
        return WikiIngestResult(
            ok=True,
            message="wiki-ingest: model output matches a previous ingest or existing wiki; skipped duplicate write.",
            written_paths=[],
            called_model=True,
        )

    entries = MemoryStore.filter_archivable_wiki_entries(
        MemoryStore.parse_wiki_archive_entries(body),
    )
    if not entries:
        return WikiIngestResult(
            ok=False,
            message="wiki-ingest: the model did not return any writable entries.",
            written_paths=[],
            called_model=True,
        )

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    written_fnames = store.merge_wiki_entries_from_archive(entries, when)
    store.wiki_ingest_remember_success(bundle_sha, body)
    slug_set = {MemoryStore.normalize_wiki_category_slug(sl) for sl, _, _, _ in entries}
    log_summary = f"{len(written_fnames)} page(s): {', '.join(sorted(written_fnames))}"
    store.append_wiki_log_line("wiki-ingest", log_summary, when=when)

    git = store.git
    if git.is_initialized():
        git.auto_commit(f"wiki-ingest: {', '.join(sorted(slug_set))}")

    files_list = ", ".join(f"`wiki/{f}`" for f in written_fnames)
    return WikiIngestResult(
        ok=True,
        message=f"Ingested {len(written_fnames)} wiki page(s) from raw/ text sources: {files_list}.",
        written_paths=list(written_fnames),
        called_model=True,
    )

"""Memory system: pure file I/O store, lightweight Consolidator, and Dream processor."""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import re
import weakref
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from nanobot.llm_wiki import (
    WIKI_DIR_NAME,
    build_wiki_context,
    ensure_standard_wiki_dirs,
    list_wiki_page_paths,
    read_schema,
)
from nanobot.llm_wiki.catalog import extract_markdown_h1
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import ensure_dir, estimate_message_tokens, estimate_prompt_tokens_chain, strip_think

from nanobot.agent.runner import AgentRunSpec, AgentRunner
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.utils.gitstore import GitStore

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session, SessionManager


# ---------------------------------------------------------------------------
# MemoryStore — pure file I/O layer
# ---------------------------------------------------------------------------

class MemoryStore:
    """Pure file I/O for memory files: MEMORY.md, history.jsonl, SOUL.md, USER.md."""

    _DEFAULT_MAX_HISTORY = 1000
    _LEGACY_ENTRY_START_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*")
    _LEGACY_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*")
    _LEGACY_RAW_MESSAGE_RE = re.compile(
        r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s+[A-Z][A-Z0-9_]*(?:\s+\[tools:\s*[^\]]+\])?:"
    )

    def __init__(self, workspace: Path, max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace = workspace
        self.max_history_entries = max_history_entries
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self.legacy_history_file = self.memory_dir / "HISTORY.md"
        self.soul_file = workspace / "SOUL.md"
        self.user_file = workspace / "USER.md"
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"
        self._git = GitStore(
            workspace,
            tracked_files=["SOUL.md", "USER.md", "memory/MEMORY.md"],
            track_wiki_markdown=True,
        )
        self._maybe_migrate_legacy_history()

    @property
    def git(self) -> GitStore:
        return self._git

    # -- generic helpers -----------------------------------------------------

    @staticmethod
    def read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _maybe_migrate_legacy_history(self) -> None:
        """One-time upgrade from legacy HISTORY.md to history.jsonl.

        The migration is best-effort and prioritizes preserving as much content
        as possible over perfect parsing.
        """
        if not self.legacy_history_file.exists():
            return
        if self.history_file.exists() and self.history_file.stat().st_size > 0:
            return

        try:
            legacy_text = self.legacy_history_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            logger.exception("Failed to read legacy HISTORY.md for migration")
            return

        entries = self._parse_legacy_history(legacy_text)
        try:
            if entries:
                self._write_entries(entries)
                last_cursor = entries[-1]["cursor"]
                self._cursor_file.write_text(str(last_cursor), encoding="utf-8")
                # Default to "already processed" so upgrades do not replay the
                # user's entire historical archive into Dream on first start.
                self._dream_cursor_file.write_text(str(last_cursor), encoding="utf-8")

            backup_path = self._next_legacy_backup_path()
            self.legacy_history_file.replace(backup_path)
            logger.info(
                "Migrated legacy HISTORY.md to history.jsonl ({} entries)",
                len(entries),
            )
        except Exception:
            logger.exception("Failed to migrate legacy HISTORY.md")

    def _parse_legacy_history(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return []

        fallback_timestamp = self._legacy_fallback_timestamp()
        entries: list[dict[str, Any]] = []
        chunks = self._split_legacy_history_chunks(normalized)

        for cursor, chunk in enumerate(chunks, start=1):
            timestamp = fallback_timestamp
            content = chunk
            match = self._LEGACY_TIMESTAMP_RE.match(chunk)
            if match:
                timestamp = match.group(1)
                remainder = chunk[match.end():].lstrip()
                if remainder:
                    content = remainder

            entries.append({
                "cursor": cursor,
                "timestamp": timestamp,
                "content": content,
            })
        return entries

    def _split_legacy_history_chunks(self, text: str) -> list[str]:
        lines = text.split("\n")
        chunks: list[str] = []
        current: list[str] = []
        saw_blank_separator = False

        for line in lines:
            if saw_blank_separator and line.strip() and current:
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            if self._should_start_new_legacy_chunk(line, current):
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            current.append(line)
            saw_blank_separator = not line.strip()

        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    def _should_start_new_legacy_chunk(self, line: str, current: list[str]) -> bool:
        if not current:
            return False
        if not self._LEGACY_ENTRY_START_RE.match(line):
            return False
        if self._is_raw_legacy_chunk(current) and self._LEGACY_RAW_MESSAGE_RE.match(line):
            return False
        return True

    def _is_raw_legacy_chunk(self, lines: list[str]) -> bool:
        first_nonempty = next((line for line in lines if line.strip()), "")
        match = self._LEGACY_TIMESTAMP_RE.match(first_nonempty)
        if not match:
            return False
        return first_nonempty[match.end():].lstrip().startswith("[RAW]")

    def _legacy_fallback_timestamp(self) -> str:
        try:
            return datetime.fromtimestamp(
                self.legacy_history_file.stat().st_mtime,
            ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _next_legacy_backup_path(self) -> Path:
        candidate = self.memory_dir / "HISTORY.md.bak"
        suffix = 2
        while candidate.exists():
            candidate = self.memory_dir / f"HISTORY.md.bak.{suffix}"
            suffix += 1
        return candidate

    # -- MEMORY.md (long-term facts) -----------------------------------------

    def read_memory(self) -> str:
        return self.read_file(self.memory_file)

    def write_memory(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    # -- SOUL.md -------------------------------------------------------------

    def read_soul(self) -> str:
        return self.read_file(self.soul_file)

    def write_soul(self, content: str) -> None:
        self.soul_file.write_text(content, encoding="utf-8")

    # -- USER.md -------------------------------------------------------------

    def read_user(self) -> str:
        return self.read_file(self.user_file)

    def write_user(self, content: str) -> None:
        self.user_file.write_text(content, encoding="utf-8")

    # -- context injection (used by context.py) ------------------------------

    def get_memory_context(self) -> str:
        long_term = self.read_memory()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    # -- wiki/ — multi-page LLM-compiled knowledge ---------------------------

    WIKI_DIR = WIKI_DIR_NAME
    WIKI_LOG_FILENAME = "log.md"
    WIKI_TITLE_REMAP_MIN_RATIO = 0.92
    WIKI_TITLE_REMAP_MIN_LEN = 8
    _WIKI_INGEST_STATE_FILE = "wiki_ingest_state.json"
    _WIKI_INGEST_BODY_HASH_CAP = 4000
    _WIKI_ROOT_PAGE_SKIP_STEMS = frozenset({"index", "schema", "log"})

    @property
    def wiki_dir(self) -> Path:
        return self.workspace / self.WIKI_DIR

    def append_wiki_log_line(self, kind: str, summary: str, *, when: str | None = None) -> None:
        """Append one section to ``wiki/log.md`` (append-only human timeline)."""
        ts = when or datetime.now().strftime("%Y-%m-%d %H:%M")
        one_line = re.sub(r"\s+", " ", summary.strip())
        if len(one_line) > 400:
            one_line = one_line[:397] + "…"
        line = f"## [{ts}] {kind} | {one_line}\n\n"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        ensure_standard_wiki_dirs(self.workspace, wiki_dir=self.WIKI_DIR)
        path = self.wiki_dir / self.WIKI_LOG_FILENAME
        if not path.is_file():
            path.write_text(
                "# Wiki log\n\n"
                "Append-only timeline of wiki actions (`/wiki-archive`, Dream, `/wiki-lint`, …).\n\n"
                "---\n\n",
                encoding="utf-8",
            )
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    def read_wiki_schema(self) -> str:
        """Return ``wiki/schema.md`` text, or empty string if missing."""
        return read_schema(self.workspace, wiki_dir=self.WIKI_DIR)

    def list_wiki_page_paths(self) -> list[str]:
        """Sorted relative paths ``wiki/**/*.md`` (posix). ``wiki/index.md`` first if present."""
        return list_wiki_page_paths(self.workspace, wiki_dir=self.WIKI_DIR)

    def get_wiki_context(
        self,
        max_total_chars: int = 24_000,
        *,
        relevance_query: str | None = None,
    ) -> str:
        """Concatenate wiki markdown for system prompt injection (token-bounded).

        Delegates to :func:`nanobot.llm_wiki.build_wiki_context` (schema first).
        When *relevance_query* is set, pages are ranked by token overlap before truncation.
        """
        return build_wiki_context(
            self.workspace,
            wiki_dir=self.WIKI_DIR,
            max_total_chars=max_total_chars,
            relevance_query=relevance_query,
        )

    @staticmethod
    def coalesce_wiki_archive_entries(
        entries: list[tuple[str, str, str, str]],
    ) -> list[tuple[str, str, str, str]]:
        """Merge same-batch rows that share normalized slug + ``page_kind`` (single index line per page)."""
        groups: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {}
        order: list[tuple[str, str]] = []
        for slug, display_title, entry_md, page_kind in entries:
            safe = MemoryStore.normalize_wiki_category_slug(slug)
            kind = MemoryStore._normalize_wiki_page_kind(page_kind)
            key = (safe, kind)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((slug, display_title, entry_md, kind))
        out: list[tuple[str, str, str, str]] = []
        for key in order:
            bucket = groups[key]
            merged_slug = key[0]
            titles = [t for _, t, _, _ in bucket if str(t).strip()]
            display_title = titles[0] if titles else ""
            parts = [em for _, _, em, _ in bucket]
            merged_md = "\n\n---\n\n".join(p.strip() for p in parts if p and str(p).strip())
            kind = key[1]
            out.append((merged_slug, display_title, merged_md, kind))
        return out

    @staticmethod
    def _wiki_rel_path_for_kind(kind: str, safe_slug: str) -> str:
        kind_n = MemoryStore._normalize_wiki_page_kind(kind)
        subdir = {
            "entity": "entities",
            "concept": "concepts",
            "source": "sources",
            "comparison": "comparisons",
        }.get(kind_n)
        if subdir:
            return f"{subdir}/{safe_slug}.md"
        return f"{safe_slug}.md"

    def _wiki_page_exists_for_kind_slug(self, kind: str, safe_slug: str) -> bool:
        rel = MemoryStore._wiki_rel_path_for_kind(kind, safe_slug)
        return (self.wiki_dir / rel).is_file()

    def _load_wiki_titles_by_kind(self) -> dict[str, list[tuple[str, str]]]:
        """Map page kind to ``(stem_slug, h1)`` for existing markdown files."""
        out: dict[str, list[tuple[str, str]]] = {
            "topic": [],
            "entity": [],
            "concept": [],
            "source": [],
            "comparison": [],
        }
        root = self.wiki_dir
        if not root.is_dir():
            return out
        for p in root.glob("*.md"):
            stem = p.stem.lower()
            if stem in self._WIKI_ROOT_PAGE_SKIP_STEMS:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out["topic"].append((stem, extract_markdown_h1(text)))
        submap = {
            "entities": "entity",
            "concepts": "concept",
            "sources": "source",
            "comparisons": "comparison",
        }
        for sub, kind in submap.items():
            d = root / sub
            if not d.is_dir():
                continue
            for p in d.glob("*.md"):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                out[kind].append((p.stem.lower(), extract_markdown_h1(text)))
        return out

    def remap_wiki_archive_slugs_by_existing_titles(
        self,
        entries: list[tuple[str, str, str, str]],
    ) -> tuple[list[tuple[str, str, str, str]], list[str]]:
        """When a new slug has no file but ``display_title`` matches an existing page H1, reuse that slug."""
        titles_by_kind = self._load_wiki_titles_by_kind()
        logs: list[str] = []
        out: list[tuple[str, str, str, str]] = []
        for slug, display_title, em, page_kind in entries:
            kind = MemoryStore._normalize_wiki_page_kind(page_kind)
            safe = MemoryStore.normalize_wiki_category_slug(slug)
            if self._wiki_page_exists_for_kind_slug(kind, safe):
                out.append((slug, display_title, em, kind))
                continue
            title_norm = MemoryStore._normalize_wiki_body_for_dedup(display_title or "")
            if len(title_norm) < self.WIKI_TITLE_REMAP_MIN_LEN:
                out.append((slug, display_title, em, kind))
                continue
            best_slug: str | None = None
            best_r = 0.0
            for cand_slug, h1_raw in titles_by_kind.get(kind, []):
                if cand_slug == safe:
                    continue
                h1_norm = MemoryStore._normalize_wiki_body_for_dedup(h1_raw)
                if len(h1_norm) < self.WIKI_TITLE_REMAP_MIN_LEN:
                    continue
                r = difflib.SequenceMatcher(None, title_norm, h1_norm).ratio()
                if r > best_r:
                    best_r = r
                    best_slug = cand_slug
            if best_slug is not None and best_r >= self.WIKI_TITLE_REMAP_MIN_RATIO:
                logs.append(f"title-remap {kind} {safe}->{best_slug} sim={best_r:.2f}")
                out.append((best_slug, display_title, em, kind))
            else:
                out.append((slug, display_title, em, kind))
        return out, logs

    def merge_wiki_entries_from_archive(
        self,
        entries: list[tuple[str, str, str, str]],
        when: str,
    ) -> list[str]:
        """Merge archivable wiki entries (merge files + topic index lines). Returns written paths under ``wiki/``."""
        merged = MemoryStore.coalesce_wiki_archive_entries(entries)
        merged, remap_logs = self.remap_wiki_archive_slugs_by_existing_titles(merged)
        merged = MemoryStore.coalesce_wiki_archive_entries(merged)
        for line in remap_logs:
            self.append_wiki_log_line("wiki-dedup", line, when=when)
        written: list[str] = []
        for slug, display_title, entry_md, page_kind in merged:
            idx_title, idx_blurb = MemoryStore.summarize_wiki_topic_entry_for_index(
                entry_md, display_title,
            )
            fname = self.merge_wiki_category_document(
                slug, display_title, entry_md, when, page_kind=page_kind,
            )
            self.append_session_archive_to_index(
                fname, when, title=idx_title, blurb=idx_blurb,
            )
            written.append(fname)
        return written

    # -- history.jsonl — append-only, JSONL format ---------------------------

    def append_history(self, entry: str) -> int:
        """Append *entry* to history.jsonl and return its auto-incrementing cursor."""
        cursor = self._next_cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        record = {"cursor": cursor, "timestamp": ts, "content": strip_think(entry.rstrip()) or entry.rstrip()}
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._cursor_file.write_text(str(cursor), encoding="utf-8")
        return cursor

    def _next_cursor(self) -> int:
        """Read the current cursor counter and return next value."""
        if self._cursor_file.exists():
            try:
                return int(self._cursor_file.read_text(encoding="utf-8").strip()) + 1
            except (ValueError, OSError):
                pass
        # Fallback: read last line's cursor from the JSONL file.
        last = self._read_last_entry()
        if last:
            return last["cursor"] + 1
        return 1

    def read_unprocessed_history(self, since_cursor: int) -> list[dict[str, Any]]:
        """Return history entries with cursor > *since_cursor*."""
        return [e for e in self._read_entries() if e["cursor"] > since_cursor]

    def compact_history(self) -> None:
        """Drop oldest entries if the file exceeds *max_history_entries*."""
        if self.max_history_entries <= 0:
            return
        entries = self._read_entries()
        if len(entries) <= self.max_history_entries:
            return
        kept = entries[-self.max_history_entries:]
        self._write_entries(kept)

    # -- JSONL helpers -------------------------------------------------------

    def _read_entries(self) -> list[dict[str, Any]]:
        """Read all entries from history.jsonl."""
        entries: list[dict[str, Any]] = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            pass
        return entries

    def _read_last_entry(self) -> dict[str, Any] | None:
        """Read the last entry from the JSONL file efficiently."""
        try:
            with open(self.history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                read_size = min(size, 4096)
                f.seek(size - read_size)
                data = f.read().decode("utf-8")
                lines = [l for l in data.split("\n") if l.strip()]
                if not lines:
                    return None
                return json.loads(lines[-1])
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        """Overwrite history.jsonl with the given entries."""
        with open(self.history_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- dream cursor --------------------------------------------------------

    def get_last_dream_cursor(self) -> int:
        if self._dream_cursor_file.exists():
            try:
                return int(self._dream_cursor_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pass
        return 0

    def set_last_dream_cursor(self, cursor: int) -> None:
        self._dream_cursor_file.write_text(str(cursor), encoding="utf-8")

    # -- message formatting utility ------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _textify_message_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def format_messages_for_archive(messages: list[dict[str, Any]]) -> str:
        """Flatten session messages to plain text for wiki archiving (includes tools)."""
        lines: list[str] = []
        for message in messages:
            role = message.get("role", "?")
            ts = str(message.get("timestamp", ""))[:19]
            extra = ""
            if role == "assistant" and message.get("tool_calls"):
                names: list[str] = []
                for tc in message.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        names.append(str(tc.get("name", "?")))
                    else:
                        names.append(str(getattr(tc, "name", "?")))
                extra = f" [tools: {', '.join(names)}]"
            body = MemoryStore._textify_message_content(message.get("content"))
            if role == "tool":
                name = message.get("name", "tool")
                clipped = body if len(body) <= 12_000 else body[:12_000] + "\n… *(truncated)*"
                lines.append(f"[{ts}] TOOL {name}: {clipped}")
                continue
            if not body.strip():
                if role == "assistant" and message.get("tool_calls"):
                    lines.append(f"[{ts}] ASSISTANT{extra}: *(no text)*")
                continue
            lines.append(f"[{ts}] {role.upper()}{extra}: {body}")
        return "\n".join(lines)

    def write_wiki_page(self, relative_path: str, content: str) -> Path:
        """Write ``content`` to ``wiki/<relative_path>`` (creates parent dirs)."""
        rel = relative_path.replace("\\", "/").lstrip("/")
        if any(part == ".." for part in rel.split("/")):
            raise ValueError("Invalid wiki path")
        ensure_standard_wiki_dirs(self.workspace, wiki_dir=self.WIKI_DIR)
        path = self.wiki_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def parse_wiki_archive_response(text: str) -> tuple[str, str, str]:
        """Parse legacy ``CATEGORY_SLUG`` / ``DISPLAY_TITLE`` headers. Returns ``(slug, display_title, entry_md)``."""
        t = text.strip().replace("\r\n", "\n")
        if not t:
            return "", "", ""
        lines = t.split("\n")
        slug = ""
        display = ""
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            m = re.match(r"^CATEGORY_SLUG:\s*([a-z0-9][a-z0-9-]{0,78})\s*$", s, re.I)
            if m:
                slug = m.group(1).lower()
                i += 1
                continue
            m = re.match(r"^DISPLAY_TITLE:\s*(.+)$", s, re.I)
            if m:
                display = m.group(1).strip()
                i += 1
                continue
            break
        entry = "\n".join(lines[i:]).strip()
        return slug, display, entry

    @staticmethod
    def _extract_json_wiki_payload(text: str) -> Any | None:
        """Parse JSON array/object from model output (optionally inside a ```json fence)."""
        t = text.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
        candidate = m.group(1).strip() if m else t
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        i = t.find("[")
        j = t.rfind("]")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _normalize_wiki_page_kind(raw: Any) -> str:
        """Map model output to ``topic`` | ``entity`` | ``concept`` | ``source``."""
        if raw is None:
            return "topic"
        s = str(raw).strip().lower()
        aliases = {
            "entities": "entity",
            "concepts": "concept",
            "sources": "source",
            "comparisons": "comparison",
            "topics": "topic",
            "general": "topic",
            "root": "topic",
            "mixed": "topic",
        }
        s = aliases.get(s, s)
        if s in ("topic", "entity", "concept", "source", "comparison"):
            return s
        return "topic"

    @staticmethod
    def _wiki_entries_from_json(data: Any) -> list[tuple[str, str, str, str]]:
        """Build entry tuples from parsed JSON: ``(slug, display_title, entry_md, page_kind)``."""
        if isinstance(data, dict):
            if isinstance(data.get("entries"), list):
                data = data["entries"]
            elif data.get("category_slug") is not None or data.get("category") is not None:
                data = [data]
            else:
                return []
        if not isinstance(data, list):
            return []
        out: list[tuple[str, str, str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            slug = str(
                item.get("category_slug") or item.get("category") or "",
            ).strip()
            title = str(
                item.get("display_title") or item.get("title") or "",
            ).strip()
            em = str(
                item.get("entry_markdown") or item.get("body") or item.get("content") or "",
            ).strip()
            kind_raw = (
                item.get("page_kind")
                or item.get("kind")
                or item.get("wiki_kind")
                or item.get("archive_kind")
            )
            kind = MemoryStore._normalize_wiki_page_kind(kind_raw)
            if not slug:
                continue
            out.append((slug.lower(), title, em, kind))
        return out

    @staticmethod
    def parse_wiki_archive_entries(text: str) -> list[tuple[str, str, str, str]]:
        """Parse JSON (preferred) or legacy header format.

        Returns ``(slug, display_title, entry_md, page_kind)``; *page_kind* is
        ``topic`` for legacy text format (wiki root) or when omitted in JSON.
        """
        t = text.strip().replace("\r\n", "\n")
        if not t:
            return []
        blob = MemoryStore._extract_json_wiki_payload(t)
        if blob is not None:
            return MemoryStore._wiki_entries_from_json(blob)
        slug, display, entry = MemoryStore.parse_wiki_archive_response(t)
        if slug:
            return [(slug, display, entry, "topic")]
        return []

    @staticmethod
    def _wiki_entry_is_empty_session_marker(entry_md: str) -> bool:
        for line in entry_md.split("\n"):
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^#\s+(.+)$", s)
            if m:
                return m.group(1).strip().lower() in ("(empty session)", "empty session")
            break
        return False

    @staticmethod
    def filter_archivable_wiki_entries(
        entries: list[tuple[str, str, str, str]],
    ) -> list[tuple[str, str, str, str]]:
        """Drop empty-session markers and blank entries."""
        out: list[tuple[str, str, str, str]] = []
        for slug, title, em, kind in entries:
            if slug.strip().lower() in ("empty-session", "empty-ingest"):
                continue
            if not em.strip():
                continue
            if MemoryStore._wiki_entry_is_empty_session_marker(em):
                continue
            out.append((slug, title, em, kind))
        return out

    @staticmethod
    def normalize_wiki_category_slug(slug: str) -> str:
        """Sanitize category slug for ``wiki/<slug>.md`` filenames."""
        s = slug.strip().lower()
        s = re.sub(r"[^a-z0-9-]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        if not s:
            s = "general"
        if s in ("index",):
            s = "index-notes"
        if len(s) > 80:
            s = s[:80].rstrip("-")
        return s

    def merge_wiki_category_document(
        self,
        slug: str,
        display_title: str,
        entry_markdown: str,
        when: str,
        *,
        page_kind: str = "topic",
    ) -> str:
        """Append an entry into a wiki page. Returns relative path under ``wiki/``.

        *page_kind* ``topic`` → ``wiki/<slug>.md``; ``entity`` | ``concept`` | ``source``
        | ``comparison`` → ``wiki/{entities|concepts|sources|comparisons}/<slug>.md``.
        """
        safe = MemoryStore.normalize_wiki_category_slug(slug)
        kind = MemoryStore._normalize_wiki_page_kind(page_kind)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        ensure_standard_wiki_dirs(self.workspace, wiki_dir=self.WIKI_DIR)
        subdir = {
            "entity": "entities",
            "concept": "concepts",
            "source": "sources",
            "comparison": "comparisons",
        }.get(kind)
        if subdir:
            dest = self.wiki_dir / subdir
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"{safe}.md"
            rel_return = f"{subdir}/{safe}.md"
        else:
            path = self.wiki_dir / f"{safe}.md"
            rel_return = f"{safe}.md"
        entry = entry_markdown.strip()
        block = f"\n\n---\n\n## {when}\n\n{entry}\n"
        title_line = (display_title.strip() or safe.replace("-", " ").title())
        if path.is_file():
            existing = path.read_text(encoding="utf-8", errors="replace").rstrip()
            path.write_text(existing + block, encoding="utf-8")
        else:
            header = (
                f"# {title_line}\n\n"
                "> One wiki file per knowledge category; new `/wiki-archive` runs append below.\n\n"
                f"---{block}"
            )
            path.write_text(header, encoding="utf-8")
        return rel_return

    @staticmethod
    def summarize_wiki_topic_entry_for_index(
        entry_markdown: str,
        display_title: str,
        *,
        blurb_max: int = 180,
    ) -> tuple[str, str]:
        """Index link label + blurb from a category entry (uses ``## Summary`` in *entry_markdown*)."""
        title = display_title.strip() or "(untitled)"
        blurb = MemoryStore._extract_index_blurb(entry_markdown.strip(), blurb_max)
        return title, blurb

    @staticmethod
    def is_wiki_archive_body_insufficient(body: str) -> bool:
        """True when there is nothing worth writing (empty output or only empty-session markers)."""
        return (
            len(
                MemoryStore.filter_archivable_wiki_entries(
                    MemoryStore.parse_wiki_archive_entries(body),
                ),
            )
            == 0
        )

    @staticmethod
    def summarize_wiki_archive_for_index(
        body: str,
        *,
        title_max: int = 100,
        blurb_max: int = 180,
    ) -> tuple[str, str]:
        """Derive (link title, one-line blurb) from archived wiki markdown for index.md."""
        text = body.strip().replace("\r\n", "\n")
        if not text:
            return "(empty)", ""

        lines = text.split("\n")
        title = ""
        start_idx = 0
        for i, raw in enumerate(lines):
            s = raw.strip()
            if not s:
                continue
            m = re.match(r"^#\s+(.+)$", s)
            if m:
                title = m.group(1).strip()
                start_idx = i + 1
                break
            if s.startswith("#"):
                title = s.lstrip("#").strip()
                start_idx = i + 1
                break

        if not title:
            title = "(untitled)"
        if len(title) > title_max:
            title = title[: title_max - 1] + "…"

        remainder = "\n".join(lines[start_idx:])
        blurb = MemoryStore._extract_index_blurb(remainder, blurb_max)
        return title, blurb

    @staticmethod
    def _extract_summary_section_after_h1(remainder: str) -> str | None:
        """Return body under ``## Summary`` until the next ``##`` heading at level 2."""
        lines = remainder.split("\n")
        for i, line in enumerate(lines):
            if re.match(r"^##\s+summary\s*$", line.strip(), re.IGNORECASE):
                parts: list[str] = []
                for j in range(i + 1, len(lines)):
                    L = lines[j].strip()
                    if re.match(r"^##\s+", L):
                        break
                    parts.append(lines[j])
                block = "\n".join(parts).strip()
                return block or None
        return None

    @staticmethod
    def _extract_index_blurb(remainder: str, max_len: int) -> str:
        """First substantive lines after the H1, flattened to one line."""
        summary_block = MemoryStore._extract_summary_section_after_h1(remainder)
        scan = summary_block if summary_block is not None else remainder

        chunks: list[str] = []
        total = 0
        for raw in scan.split("\n"):
            s = raw.strip()
            if not s or s == "---":
                continue
            if s.startswith("#"):
                continue
            if s.startswith(("- ", "* ")):
                s = re.sub(r"^[\-\*]\s+", "", s)
            elif re.match(r"^\d+\.\s+", s):
                s = re.sub(r"^\d+\.\s+", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            if not s:
                continue
            chunks.append(s)
            total += len(s) + 2
            if total >= max_len:
                break

        if not chunks:
            for raw in remainder.split("\n"):
                s = raw.strip()
                if s and not s.startswith("#"):
                    chunks.append(re.sub(r"\s+", " ", s))
                    break

        if not chunks:
            return ""

        out = " · ".join(chunks)
        if len(out) > max_len:
            return out[: max_len - 1] + "…"
        return out

    def append_session_archive_to_index(
        self,
        wiki_filename: str,
        when: str,
        *,
        title: str = "",
        blurb: str = "",
    ) -> None:
        """Append a bullet under ``## Topic archives`` (or legacy ``## Session archives``).

        *title* is the link label. *blurb* is a short plain-text summary for search.
        """
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        ensure_standard_wiki_dirs(self.workspace, wiki_dir=self.WIKI_DIR)
        index_path = self.wiki_dir / "index.md"
        label = title.strip() or wiki_filename
        line = f"- {when} — [{label}]({wiki_filename})"
        if blurb.strip():
            line += f" — {blurb.strip()}"
        marker_primary = "## Topic archives"
        marker_legacy = "## Session archives"
        if not index_path.exists():
            index_path.write_text(
                "# Wiki index\n\n"
                "Multi-page knowledge.\n\n"
                "---\n\n"
                f"{marker_primary}\n\n"
                f"{line}\n",
                encoding="utf-8",
            )
            return
        text = index_path.read_text(encoding="utf-8")
        for marker in (marker_primary, marker_legacy):
            if marker in text:
                head, sep, tail = text.partition(marker)
                new_text = head + sep + tail.rstrip() + "\n" + line + "\n"
                index_path.write_text(new_text, encoding="utf-8")
                return
        new_text = text.rstrip() + "\n\n---\n\n" + marker_primary + "\n\n" + line + "\n"
        index_path.write_text(new_text, encoding="utf-8")

    def read_wiki_index(self) -> str:
        """Return ``wiki/index.md`` text, or empty string if missing."""
        p = self.wiki_dir / "index.md"
        if not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    _WIKI_ARCHIVE_DEDUP_FILE = "wiki_archive_dedup.json"
    _WIKI_ARCHIVE_DEDUP_CAP = 4000

    def _wiki_archive_dedup_path(self) -> Path:
        return self.memory_dir / self._WIKI_ARCHIVE_DEDUP_FILE

    def _load_wiki_archive_dedup(self) -> dict[str, Any]:
        p = self._wiki_archive_dedup_path()
        if not p.is_file():
            return {"transcript_sha256": [], "body_sha256": []}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"transcript_sha256": [], "body_sha256": []}
        data.setdefault("transcript_sha256", [])
        data.setdefault("body_sha256", [])
        return data

    def _save_wiki_archive_dedup(self, data: dict[str, Any]) -> None:
        p = self._wiki_archive_dedup_path()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    @staticmethod
    def _normalize_wiki_body_for_dedup(text: str) -> str:
        t = text.strip().lower()
        return re.sub(r"\s+", " ", t)

    def wiki_archive_transcript_already_archived(self, transcript_sha256: str) -> bool:
        """True if this exact session transcript was already successfully archived."""
        return transcript_sha256 in self._load_wiki_archive_dedup().get("transcript_sha256", [])

    def wiki_archive_should_skip_duplicate_body(
        self,
        body: str,
        *,
        similarity_threshold: float = 0.94,
    ) -> bool:
        """True when generated markdown matches a prior archive (hash or high similarity)."""
        norm = MemoryStore._normalize_wiki_body_for_dedup(body)
        if len(norm) < 32:
            return False
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if digest in self._load_wiki_archive_dedup().get("body_sha256", []):
            return True
        return self._wiki_archive_near_duplicate_file(norm, similarity_threshold=similarity_threshold)

    def _wiki_archive_near_duplicate_file(self, norm_new: str, *, similarity_threshold: float) -> bool:
        root = self.wiki_dir
        if not root.is_dir():
            return False
        candidates: list[Path] = []
        for p in root.rglob("*.md"):
            rel = p.relative_to(root)
            if rel.name.lower() == "index.md":
                continue
            if rel.parts == ("schema.md",):
                continue
            candidates.append(p)
        paths = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:40]
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            norm_o = MemoryStore._normalize_wiki_body_for_dedup(raw)
            if len(norm_o) < 32:
                continue
            # Avoid comparing a short new entry to a long accumulated category page.
            if len(norm_o) > max(3500, len(norm_new) * 12):
                continue
            ratio = difflib.SequenceMatcher(None, norm_new, norm_o).ratio()
            if ratio >= similarity_threshold:
                return True
        return False

    def wiki_archive_remember_success(self, transcript_sha256: str, body: str) -> None:
        """Record transcript and body fingerprints after a successful wiki-archive write."""
        data = self._load_wiki_archive_dedup()
        ts: list[str] = data.setdefault("transcript_sha256", [])
        if transcript_sha256 not in ts:
            ts.append(transcript_sha256)
        while len(ts) > self._WIKI_ARCHIVE_DEDUP_CAP:
            ts.pop(0)

        norm = MemoryStore._normalize_wiki_body_for_dedup(body)
        bh = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        bs: list[str] = data.setdefault("body_sha256", [])
        if bh not in bs:
            bs.append(bh)
        while len(bs) > self._WIKI_ARCHIVE_DEDUP_CAP:
            bs.pop(0)

        self._save_wiki_archive_dedup(data)

    def wiki_archive_remember_transcript_only(self, transcript_sha256: str) -> None:
        """Remember transcript hash when skipping duplicate body so the same window is not reprocessed."""
        data = self._load_wiki_archive_dedup()
        ts: list[str] = data.setdefault("transcript_sha256", [])
        if transcript_sha256 not in ts:
            ts.append(transcript_sha256)
        while len(ts) > self._WIKI_ARCHIVE_DEDUP_CAP:
            ts.pop(0)
        self._save_wiki_archive_dedup(data)

    def _wiki_ingest_state_path(self) -> Path:
        return self.memory_dir / self._WIKI_INGEST_STATE_FILE

    def _load_wiki_ingest_state(self) -> dict[str, Any]:
        p = self._wiki_ingest_state_path()
        if not p.is_file():
            return {"last_success_bundle_sha256": "", "body_sha256": []}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"last_success_bundle_sha256": "", "body_sha256": []}
        if not isinstance(data, dict):
            return {"last_success_bundle_sha256": "", "body_sha256": []}
        data.setdefault("last_success_bundle_sha256", "")
        data.setdefault("body_sha256", [])
        return data

    def _save_wiki_ingest_state(self, data: dict[str, Any]) -> None:
        p = self._wiki_ingest_state_path()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    def wiki_ingest_bundle_matches_last_success(self, bundle_sha256: str) -> bool:
        """True when raw file bundle matches the last successful wiki-ingest."""
        if not bundle_sha256:
            return False
        prev = str(self._load_wiki_ingest_state().get("last_success_bundle_sha256") or "")
        return prev != "" and prev == bundle_sha256

    def wiki_ingest_should_skip_duplicate_body(
        self,
        body: str,
        *,
        similarity_threshold: float = 0.94,
    ) -> bool:
        """True when ingest JSON output matches a prior ingest or existing wiki (hash or high similarity)."""
        norm = MemoryStore._normalize_wiki_body_for_dedup(body)
        if len(norm) < 32:
            return False
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if digest in self._load_wiki_ingest_state().get("body_sha256", []):
            return True
        return self._wiki_archive_near_duplicate_file(norm, similarity_threshold=similarity_threshold)

    def wiki_ingest_remember_success(self, bundle_sha256: str, body: str) -> None:
        """Record bundle + body fingerprints after a successful wiki-ingest write."""
        data = self._load_wiki_ingest_state()
        data["last_success_bundle_sha256"] = bundle_sha256
        norm = MemoryStore._normalize_wiki_body_for_dedup(body)
        bh = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        bs: list[str] = data.setdefault("body_sha256", [])
        if bh not in bs:
            bs.append(bh)
        while len(bs) > self._WIKI_INGEST_BODY_HASH_CAP:
            bs.pop(0)
        self._save_wiki_ingest_state(data)

    def wiki_ingest_remember_duplicate_body_skip(self, bundle_sha256: str, body: str) -> None:
        """Record state when skipping ingest because output is a near-duplicate."""
        data = self._load_wiki_ingest_state()
        data["last_success_bundle_sha256"] = bundle_sha256
        norm = MemoryStore._normalize_wiki_body_for_dedup(body)
        bh = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        bs: list[str] = data.setdefault("body_sha256", [])
        if bh not in bs:
            bs.append(bh)
        while len(bs) > self._WIKI_INGEST_BODY_HASH_CAP:
            bs.pop(0)
        self._save_wiki_ingest_state(data)

    def raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages to history.jsonl without LLM summarization."""
        self.append_history(
            f"[RAW] {len(messages)} messages\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )



# ---------------------------------------------------------------------------
# Consolidator — lightweight token-budget triggered consolidation
# ---------------------------------------------------------------------------


class Consolidator:
    """Lightweight consolidation: summarizes evicted messages into history.jsonl."""

    _MAX_CONSOLIDATION_ROUNDS = 5
    _MAX_CHUNK_MESSAGES = 60  # hard cap per consolidation round

    _SAFETY_BUFFER = 1024  # extra headroom for tokenizer estimation drift

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        max_completion_tokens: int = 4096,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def _cap_consolidation_boundary(
        self,
        session: Session,
        end_idx: int,
    ) -> int | None:
        """Clamp the chunk size without breaking the user-turn boundary."""
        start = session.last_consolidated
        if end_idx - start <= self._MAX_CHUNK_MESSAGES:
            return end_idx

        capped_end = start + self._MAX_CHUNK_MESSAGES
        for idx in range(capped_end, start, -1):
            if session.messages[idx].get("role") == "user":
                return idx
        return None

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=0)
        channel, chat_id = (session.key.split(":", 1) if ":" in session.key else (None, None))
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    async def archive(self, messages: list[dict]) -> str | None:
        """Summarize messages via LLM and append to history.jsonl.

        Returns the summary text on success, None if nothing to archive.
        """
        if not messages:
            return None
        try:
            formatted = MemoryStore._format_messages(messages)
            response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": render_template(
                            "agent/consolidator_archive.md",
                            strip=True,
                        ),
                    },
                    {"role": "user", "content": formatted},
                ],
                tools=None,
                tool_choice=None,
            )
            summary = response.content or "[no summary]"
            self.store.append_history(summary)
            return summary
        except Exception:
            logger.warning("Consolidation LLM call failed, raw-dumping to history")
            self.store.raw_archive(messages)
            return None

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within safe budget.

        The budget reserves space for completion tokens and a safety buffer
        so the LLM request never exceeds the context window.
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
            target = budget // 2
            try:
                estimated, source = self.estimate_session_prompt_tokens(session)
            except Exception:
                logger.exception("Token estimation failed for {}", session.key)
                estimated, source = 0, "error"
            if estimated <= 0:
                return
            if estimated < budget:
                unconsolidated_count = len(session.messages) - session.last_consolidated
                logger.debug(
                    "Token consolidation idle {}: {}/{} via {}, msgs={}",
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    unconsolidated_count,
                )
                return

            for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(
                        "Token consolidation: no safe boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                end_idx = boundary[0]
                end_idx = self._cap_consolidation_boundary(session, end_idx)
                if end_idx is None:
                    logger.debug(
                        "Token consolidation: no capped boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                    round_num,
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    len(chunk),
                )
                if not await self.archive(chunk):
                    return
                session.last_consolidated = end_idx
                self.sessions.save(session)

                try:
                    estimated, source = self.estimate_session_prompt_tokens(session)
                except Exception:
                    logger.exception("Token estimation failed for {}", session.key)
                    estimated, source = 0, "error"
                if estimated <= 0:
                    return


# ---------------------------------------------------------------------------
# Dream — heavyweight cron-scheduled memory consolidation
# ---------------------------------------------------------------------------


class Dream:
    """Two-phase memory processor: analyze history.jsonl, then edit files via AgentRunner.

    Phase 1 produces an analysis summary (plain LLM call).
    Phase 2 delegates to AgentRunner with read_file / edit_file tools so the
    LLM can make targeted, incremental edits instead of replacing entire files.
    """

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        max_batch_size: int = 20,
        max_iterations: int = 10,
        max_tool_result_chars: int = 16_000,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_iterations = max_iterations
        self.max_tool_result_chars = max_tool_result_chars
        self._runner = AgentRunner(provider)
        self._tools = self._build_tools()

    # -- tool registry -------------------------------------------------------

    def _build_tools(self) -> ToolRegistry:
        """Build a minimal tool registry for the Dream agent."""
        from nanobot.agent.skills import BUILTIN_SKILLS_DIR
        from nanobot.agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool

        tools = ToolRegistry()
        workspace = self.store.workspace
        # Allow reading builtin skills for reference during skill creation
        extra_read = [BUILTIN_SKILLS_DIR] if BUILTIN_SKILLS_DIR.exists() else None
        tools.register(ReadFileTool(
            workspace=workspace,
            allowed_dir=workspace,
            extra_allowed_dirs=extra_read,
        ))
        tools.register(EditFileTool(workspace=workspace, allowed_dir=workspace))
        # write_file resolves relative paths from workspace root, but can only
        # write under skills/ so the prompt can safely use skills/<name>/SKILL.md.
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        tools.register(WriteFileTool(workspace=workspace, allowed_dir=skills_dir))
        return tools

    # -- skill listing --------------------------------------------------------

    def _list_existing_skills(self) -> list[str]:
        """List existing skills as 'name — description' for dedup context."""
        import re as _re

        from nanobot.agent.skills import BUILTIN_SKILLS_DIR

        _DESC_RE = _re.compile(r"^description:\s*(.+)$", _re.MULTILINE | _re.IGNORECASE)
        entries: dict[str, str] = {}
        for base in (self.store.workspace / "skills", BUILTIN_SKILLS_DIR):
            if not base.exists():
                continue
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                skill_md = d / "SKILL.md"
                if not skill_md.exists():
                    continue
                # Prefer workspace skills over builtin (same name)
                if d.name in entries and base == BUILTIN_SKILLS_DIR:
                    continue
                content = skill_md.read_text(encoding="utf-8")[:500]
                m = _DESC_RE.search(content)
                desc = m.group(1).strip() if m else "(no description)"
                entries[d.name] = desc
        return [f"{name} — {desc}" for name, desc in sorted(entries.items())]

    # -- main entry ----------------------------------------------------------

    async def run(self) -> bool:
        """Process unprocessed history entries. Returns True if work was done."""
        from nanobot.agent.skills import BUILTIN_SKILLS_DIR

        last_cursor = self.store.get_last_dream_cursor()
        entries = self.store.read_unprocessed_history(since_cursor=last_cursor)
        if not entries:
            return False

        batch = entries[: self.max_batch_size]
        logger.info(
            "Dream: processing {} entries (cursor {}→{}), batch={}",
            len(entries), last_cursor, batch[-1]["cursor"], len(batch),
        )

        # Build history text for LLM
        history_text = "\n".join(
            f"[{e['timestamp']}] {e['content']}" for e in batch
        )

        # Current file contents
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_memory = self.store.read_memory() or "(empty)"
        current_soul = self.store.read_soul() or "(empty)"
        current_user = self.store.read_user() or "(empty)"
        wiki_snapshot = self.store.get_wiki_context(max_total_chars=32_000)
        wiki_block = (
            f"\n\n## Wiki (`{MemoryStore.WIKI_DIR}/`) — {len(wiki_snapshot)} chars\n{wiki_snapshot}"
            if wiki_snapshot
            else ""
        )
        file_context = (
            f"## Current Date\n{current_date}\n\n"
            f"## Current MEMORY.md ({len(current_memory)} chars)\n{current_memory}\n\n"
            f"## Current SOUL.md ({len(current_soul)} chars)\n{current_soul}\n\n"
            f"## Current USER.md ({len(current_user)} chars)\n{current_user}"
            f"{wiki_block}"
        )

        # Phase 1: Analyze (no skills list — dedup is Phase 2's job)
        phase1_prompt = (
            f"## Conversation History\n{history_text}\n\n{file_context}"
        )

        try:
            phase1_response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": render_template("agent/dream_phase1.md", strip=True),
                    },
                    {"role": "user", "content": phase1_prompt},
                ],
                tools=None,
                tool_choice=None,
            )
            analysis = phase1_response.content or ""
            logger.debug("Dream Phase 1 analysis ({} chars): {}", len(analysis), analysis[:500])
        except Exception:
            logger.exception("Dream Phase 1 failed")
            return False

        # Phase 2: Delegate to AgentRunner with read_file / edit_file
        existing_skills = self._list_existing_skills()
        skills_section = ""
        if existing_skills:
            skills_section = (
                "\n\n## Existing Skills\n"
                + "\n".join(f"- {s}" for s in existing_skills)
            )
        phase2_prompt = f"## Analysis Result\n{analysis}\n\n{file_context}{skills_section}"

        tools = self._tools
        skill_creator_path = BUILTIN_SKILLS_DIR / "skill-creator" / "SKILL.md"
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": render_template(
                    "agent/dream_phase2.md",
                    strip=True,
                    skill_creator_path=str(skill_creator_path),
                ),
            },
            {"role": "user", "content": phase2_prompt},
        ]

        try:
            result = await self._runner.run(AgentRunSpec(
                initial_messages=messages,
                tools=tools,
                model=self.model,
                max_iterations=self.max_iterations,
                max_tool_result_chars=self.max_tool_result_chars,
                fail_on_tool_error=False,
            ))
            logger.debug(
                "Dream Phase 2 complete: stop_reason={}, tool_events={}",
                result.stop_reason, len(result.tool_events),
            )
            for ev in (result.tool_events or []):
                logger.info("Dream tool_event: name={}, status={}, detail={}", ev.get("name"), ev.get("status"), ev.get("detail", "")[:200])
        except Exception:
            logger.exception("Dream Phase 2 failed")
            result = None

        # Build changelog from tool events
        changelog: list[str] = []
        if result and result.tool_events:
            for event in result.tool_events:
                if event["status"] == "ok":
                    changelog.append(f"{event['name']}: {event['detail']}")

        # Advance cursor — always, to avoid re-processing Phase 1
        new_cursor = batch[-1]["cursor"]
        self.store.set_last_dream_cursor(new_cursor)
        self.store.compact_history()

        if result and result.stop_reason == "completed":
            logger.info(
                "Dream done: {} change(s), cursor advanced to {}",
                len(changelog), new_cursor,
            )
        else:
            reason = result.stop_reason if result else "exception"
            logger.warning(
                "Dream incomplete ({}): cursor advanced to {}",
                reason, new_cursor,
            )

        # Git auto-commit (only when there are actual changes)
        if changelog and self.store.git.is_initialized():
            ts = batch[-1]["timestamp"]
            sha = self.store.git.auto_commit(f"dream: {ts}, {len(changelog)} change(s)")
            if sha:
                logger.info("Dream commit: {}", sha)

        if changelog:
            dream_summary = f"{len(changelog)} change(s): " + "; ".join(changelog[:6])
            if len(changelog) > 6:
                dream_summary += " …"
            self.store.append_wiki_log_line("dream", dream_summary)

        return True

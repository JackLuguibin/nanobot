"""Shared wiki-archive execution (manual /wiki-archive and auto threshold trigger)."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING, Any

from nanobot.agent.memory import MemoryStore
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.llm_wiki import read_schema
from nanobot.llm_wiki.automation import maybe_lint_after_wiki_write

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.session.manager import Session


async def run_wiki_archive_for_session(
    loop: AgentLoop,
    session: Session,
    msg: InboundMessage,
    *,
    append_transcript_messages: list[dict[str, Any]] | None = None,
    brief_success: bool = False,
    estimated_tokens: int | None = None,
    threshold_tokens: int | None = None,
) -> OutboundMessage | None:
    """Archive unconsolidated session messages into ``wiki/`` and reset session to the index.

    *append_transcript_messages* — optional extra messages (e.g. the inbound user turn not yet
    persisted) included in the transcript hash and model prompt only.

    Returns *None* only if there is nothing to archive (empty chunk and no append). Otherwise
    returns an :class:`OutboundMessage` (success, skip, or error).
    """
    from nanobot.utils.helpers import strip_think
    from nanobot.utils.prompt_templates import render_template

    store = loop.consolidator.store

    chunk = session.messages[session.last_consolidated :]
    extra = append_transcript_messages or []
    effective = list(chunk) + list(extra)
    if not effective:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=(
                "No messages to archive in the current window (older content may already be in "
                "memory/history.jsonl, or the session is empty)."
            ),
            metadata=dict(msg.metadata or {}),
        )

    transcript_raw = MemoryStore.format_messages_for_archive(effective)
    if not transcript_raw.strip():
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="No substantive conversation content to archive.",
            metadata=dict(msg.metadata or {}),
        )

    transcript_sha256 = hashlib.sha256(transcript_raw.encode("utf-8")).hexdigest()
    if store.wiki_archive_transcript_already_archived(transcript_sha256):
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="This session matches content already archived; skipped duplicate archive.",
            metadata=dict(msg.metadata or {}),
        )

    transcript = transcript_raw
    max_chars = 120_000
    if len(transcript) > max_chars:
        half = max_chars // 2
        transcript = (
            transcript[:half]
            + "\n\n… *[transcript truncated for archiving]*\n\n"
            + transcript[-half:]
        )

    pre_notice = (
        "Auto wiki-archive: context threshold reached. Starting archive (calling the model). "
        "This may take a moment."
        if brief_success
        else "Starting wiki archive (calling the model). This may take a moment."
    )
    meta = {**dict(msg.metadata or {}), "render_as": "text"}
    await loop.bus.publish_outbound(
        OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=pre_notice,
            metadata=meta,
        )
    )

    try:
        wiki_schema = read_schema(store.workspace).strip()
        response = await loop.provider.chat_with_retry(
            model=loop.model,
            messages=[
                {
                    "role": "system",
                    "content": render_template(
                        "agent/wiki_archive.md",
                        strip=True,
                        wiki_schema=wiki_schema,
                    ),
                },
                {"role": "user", "content": f"## Transcript\n\n{transcript}"},
            ],
            tools=None,
            tool_choice=None,
        )
    except Exception as e:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=f"Archive failed: {e}",
            metadata=dict(msg.metadata or {}),
        )

    body = strip_think(response.content or "").strip()
    if body.startswith("```"):
        lines = body.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()

    if store.wiki_archive_should_skip_duplicate_body(body):
        store.wiki_archive_remember_transcript_only(transcript_sha256)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="Generated result is too similar to an existing wiki archive; skipped write.",
            metadata=dict(msg.metadata or {}),
        )

    entries = MemoryStore.filter_archivable_wiki_entries(
        MemoryStore.parse_wiki_archive_entries(body),
    )
    if not entries:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="Nothing to archive: no substantive content to save (empty session or nothing to distill).",
            metadata=dict(msg.metadata or {}),
        )

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    written_fnames = store.merge_wiki_entries_from_archive(entries, when)
    slug_set = {MemoryStore.normalize_wiki_category_slug(sl) for sl, _, _, _ in entries}

    git = store.git
    if git.is_initialized():
        git.auto_commit(f"wiki-archive: {', '.join(sorted(slug_set))}")

    store.wiki_archive_remember_success(transcript_sha256, body)

    log_summary = f"{len(written_fnames)} file(s): {', '.join(sorted(written_fnames))}"
    if brief_success:
        log_summary = f"auto threshold: {log_summary}"
    store.append_wiki_log_line("wiki-archive", log_summary, when=when)

    maybe_lint_after_wiki_write(
        store,
        enabled=getattr(loop, "auto_wiki_lint_after_wiki_write", False),
        source="wiki-archive",
    )

    files_list = ", ".join(f"`wiki/{f}`" for f in written_fnames)
    index_text = store.read_wiki_index()
    replacement = (
        f"[Session context archived to {files_list} — prior messages cleared.]\n\n"
        "Below is the full **wiki/index.md** as the anchor for continuing this conversation:\n\n"
        f"{index_text if index_text else '*(index empty)*'}"
    )

    n = len(effective)
    session.clear()
    session.add_message("user", replacement)
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)

    n_topics = len(entries)
    if brief_success:
        est = estimated_tokens if estimated_tokens is not None else 0
        thr = threshold_tokens if threshold_tokens is not None else 0
        content = (
            f"[Auto wiki-archive] Estimated prompt ~{est} tokens (≥ threshold ~{thr} tokens). "
            f"Wrote {n_topics} topic(s) to {files_list}. Session replaced with wiki index."
        )
    else:
        content = (
            f"Wrote {n_topics} topic(s) from {n} message(s) to {files_list} and updated the index; "
            "session replaced with the full index (one placeholder message)."
        )
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=content,
        metadata=dict(msg.metadata or {}),
    )

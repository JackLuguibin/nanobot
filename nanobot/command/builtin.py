"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

from nanobot import __version__
from nanobot.agent.memory import MemoryStore
from nanobot.llm_wiki import read_schema
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.utils.helpers import build_status_content
from nanobot.utils.restart import set_restart_notice_to_env


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    tasks = loop._active_tasks.pop(msg.session_key, [])
    cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
    for t in tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    sub_cancelled = await loop.subagents.cancel_by_session(msg.session_key)
    total = cancelled + sub_cancelled
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content,
        metadata=dict(msg.metadata or {})
    )


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg
    set_restart_notice_to_env(channel=msg.channel, chat_id=msg.chat_id)

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        metadata=dict(msg.metadata or {})
    )


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    ctx_est = 0
    try:
        ctx_est, _ = loop.consolidator.estimate_session_prompt_tokens(session)
    except Exception:
        pass
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)
    
    # Fetch web search provider usage (best-effort, never blocks the response)
    search_usage_text: str | None = None
    try:
        from nanobot.utils.searchusage import fetch_search_usage
        web_cfg = getattr(loop, "web_config", None)
        search_cfg = getattr(web_cfg, "search", None) if web_cfg else None
        if search_cfg is not None:
            provider = getattr(search_cfg, "provider", "duckduckgo")
            api_key = getattr(search_cfg, "api_key", "") or None
            usage = await fetch_search_usage(provider=provider, api_key=api_key)
            search_usage_text = usage.format()
    except Exception:
        pass  # Never let usage fetch break /status
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__, model=loop.model,
            start_time=loop._start_time, last_usage=loop._last_usage,
            context_window_tokens=loop.context_window_tokens,
            session_msg_count=len(session.get_history(max_messages=0)),
            context_tokens_estimate=ctx_est,
            search_usage_text=search_usage_text,
        ),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_wiki_archive(ctx: CommandContext) -> OutboundMessage:
    """Summarize the current session window into ``wiki/``, then replace history with the index."""
    from nanobot.command.wiki_archive import run_wiki_archive_for_session

    loop = ctx.loop
    msg = ctx.msg
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    out = await run_wiki_archive_for_session(
        loop,
        session,
        msg,
        append_transcript_messages=None,
        brief_success=False,
    )
    assert out is not None
    return out


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Start a fresh session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated:]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot))
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content="New session started.",
        metadata=dict(ctx.msg.metadata or {})
    )


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Manually trigger a Dream consolidation run."""
    import time

    loop = ctx.loop
    msg = ctx.msg

    async def _run_dream():
        t0 = time.monotonic()
        try:
            did_work = await loop.dream.run()
            elapsed = time.monotonic() - t0
            if did_work:
                content = f"Dream completed in {elapsed:.1f}s."
            else:
                content = "Dream: nothing to process."
        except Exception as e:
            elapsed = time.monotonic() - t0
            content = f"Dream failed after {elapsed:.1f}s: {e}"
        await loop.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    asyncio.create_task(_run_dream())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Dreaming...",
    )


def _extract_changed_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith("b/"):
            path = path[2:]
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _format_changed_files(diff: str) -> str:
    files = _extract_changed_files(diff)
    if not files:
        return "No tracked memory files changed."
    return ", ".join(f"`{path}`" for path in files)


def _format_dream_log_content(commit, diff: str, *, requested_sha: str | None = None) -> str:
    files_line = _format_changed_files(diff)
    lines = [
        "## Dream Update",
        "",
        "Here is the selected Dream memory change." if requested_sha else "Here is the latest Dream memory change.",
        "",
        f"- Commit: `{commit.sha}`",
        f"- Time: {commit.timestamp}",
        f"- Changed files: {files_line}",
    ]
    if diff:
        lines.extend([
            "",
            f"Use `/dream-restore {commit.sha}` to undo this change.",
            "",
            "```diff",
            diff.rstrip(),
            "```",
        ])
    else:
        lines.extend([
            "",
            "Dream recorded this version, but there is no file diff to display.",
        ])
    return "\n".join(lines)


def _format_dream_restore_list(commits: list) -> str:
    lines = [
        "## Dream Restore",
        "",
        "Choose a Dream memory version to restore. Latest first:",
        "",
    ]
    for c in commits:
        lines.append(f"- `{c.sha}` {c.timestamp} - {c.message.splitlines()[0]}")
    lines.extend([
        "",
        "Preview a version with `/dream-log <sha>` before restoring it.",
        "Restore a version with `/dream-restore <sha>`.",
    ])
    return "\n".join(lines)


async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    """Show what the last Dream changed.

    Default: diff of the latest commit (HEAD~1 vs HEAD).
    With /dream-log <sha>: diff of that specific commit.
    """
    store = ctx.loop.consolidator.store
    git = store.git

    if not git.is_initialized():
        if store.get_last_dream_cursor() == 0:
            msg = "Dream has not run yet. Run `/dream`, or wait for the next scheduled Dream cycle."
        else:
            msg = "Dream history is not available because memory versioning is not initialized."
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content=msg, metadata={"render_as": "text"},
        )

    args = ctx.args.strip()

    if args:
        # Show diff of a specific commit
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        if not result:
            content = (
                f"Couldn't find Dream change `{sha}`.\n\n"
                "Use `/dream-restore` to list recent versions, "
                "or `/dream-log` to inspect the latest one."
            )
        else:
            commit, diff = result
            content = _format_dream_log_content(commit, diff, requested_sha=sha)
    else:
        # Default: show the latest commit's diff
        commits = git.log(max_entries=1)
        result = git.show_commit_diff(commits[0].sha) if commits else None
        if result:
            commit, diff = result
            content = _format_dream_log_content(commit, diff)
        else:
            content = "Dream memory has no saved versions yet."

    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    """Restore memory files from a previous dream commit.

    Usage:
        /dream-restore          — list recent commits
        /dream-restore <sha>    — revert a specific commit
    """
    store = ctx.loop.consolidator.store
    git = store.git
    if not git.is_initialized():
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Dream history is not available because memory versioning is not initialized.",
        )

    args = ctx.args.strip()
    if not args:
        # Show recent commits for the user to pick
        commits = git.log(max_entries=10)
        if not commits:
            content = "Dream memory has no saved versions to restore yet."
        else:
            content = _format_dream_restore_list(commits)
    else:
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        changed_files = _format_changed_files(result[1]) if result else "the tracked memory files"
        new_sha = git.revert(sha)
        if new_sha:
            content = (
                f"Restored Dream memory to the state before `{sha}`.\n\n"
                f"- New safety commit: `{new_sha}`\n"
                f"- Restored files: {changed_files}\n\n"
                f"Use `/dream-log {new_sha}` to inspect the restore diff."
            )
        else:
            content = (
                f"Couldn't restore Dream change `{sha}`.\n\n"
                "It may not exist, or it may be the first saved version with no earlier state to restore."
            )
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


async def cmd_wiki_ingest(ctx: CommandContext) -> OutboundMessage:
    """Read text files from ``raw/sources/`` and merge structured notes into ``wiki/``."""
    from nanobot.utils.helpers import strip_think
    from nanobot.utils.prompt_templates import render_template
    from nanobot.llm_wiki.raw import ensure_raw_directories, list_raw_source_files

    loop = ctx.loop
    msg = ctx.msg
    store = loop.consolidator.store
    ws = store.workspace
    ensure_raw_directories(ws)
    paths = list_raw_source_files(ws)
    arg = (ctx.args or "").strip()
    if arg:
        paths = [p for p in paths if arg.lower() in p.lower()]
    if not paths:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=(
                "No ingestable text files (.md/.txt, etc.) under `raw/sources/`. "
                "Add sources there (immutable), or use `/wiki-ingest <keyword>` to filter by path."
            ),
            metadata=dict(msg.metadata or {}),
        )

    max_files, max_chars = 12, 100_000
    chunks: list[str] = []
    for rel in paths[:max_files]:
        p = ws / rel
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            chunks.append(f"## {rel}\n\n*(unreadable: {e})*")
            continue
        if len(body) > max_chars:
            body = body[:max_chars] + "\n\n… *(truncated)*\n"
        chunks.append(f"## {rel}\n\n{body}")
    bundle = "\n\n---\n\n".join(chunks)

    wiki_schema = read_schema(ws).strip()
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
                    ),
                },
                {"role": "user", "content": f"## Raw files\n\n{bundle}"},
            ],
            tools=None,
            tool_choice=None,
        )
    except Exception as e:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=f"wiki-ingest: model call failed: {e}",
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

    entries = MemoryStore.filter_archivable_wiki_entries(
        MemoryStore.parse_wiki_archive_entries(body),
    )
    if not entries:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="wiki-ingest: the model did not return any writable entries.",
            metadata=dict(msg.metadata or {}),
        )

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    written_fnames = store.merge_wiki_entries_from_archive(entries, when)
    slug_set = {MemoryStore.normalize_wiki_category_slug(sl) for sl, _, _, _ in entries}
    log_summary = f"{len(written_fnames)} page(s): {', '.join(sorted(written_fnames))}"
    store.append_wiki_log_line("wiki-ingest", log_summary, when=when)

    git = store.git
    if git.is_initialized():
        git.auto_commit(f"wiki-ingest: {', '.join(sorted(slug_set))}")

    files_list = ", ".join(f"`wiki/{f}`" for f in written_fnames)
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=(
            f"Ingested {len(written_fnames)} wiki page(s) from raw/sources: {files_list}."
        ),
        metadata=dict(msg.metadata or {}),
    )


async def cmd_wiki_lint(ctx: CommandContext) -> OutboundMessage:
    """Scan wiki for broken wikilinks and orphan pages."""
    from nanobot.llm_wiki.lint import format_wiki_lint_message, run_wiki_lint

    store = ctx.loop.consolidator.store
    report = run_wiki_lint(store.workspace)
    text = format_wiki_lint_message(report)
    summary = f"{len(report.dead_links)} dead link(s), {len(report.orphan_pages)} orphan(s)"
    store.append_wiki_log_line("wiki-lint", summary)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=text,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_wiki_save_answer(ctx: CommandContext) -> OutboundMessage:
    """Save the last assistant message to ``wiki/queries/<slug>.md``."""
    from nanobot.utils.helpers import strip_think

    loop = ctx.loop
    msg = ctx.msg
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    store = loop.consolidator.store

    assistant_text = ""
    for m in reversed(session.messages or []):
        if m.get("role") != "assistant":
            continue
        raw = m.get("content")
        if isinstance(raw, str) and raw.strip():
            assistant_text = strip_think(raw).strip()
            break
    if not assistant_text:
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="No previous assistant reply to save.",
            metadata=dict(msg.metadata or {}),
        )

    arg = (ctx.args or "").strip()
    if arg:
        safe = MemoryStore.normalize_wiki_category_slug(arg)
    else:
        safe = f"answer-{datetime.now().strftime('%Y%m%d-%H%M')}"

    qdir = store.wiki_dir / "queries"
    qdir.mkdir(parents=True, exist_ok=True)
    path = qdir / f"{safe}.md"
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_section = f"## {when}\n\n{assistant_text}\n"
    if path.is_file():
        existing = path.read_text(encoding="utf-8", errors="replace").rstrip()
        content = existing + "\n\n---\n\n" + new_section
    else:
        content = (
            "# Saved answer\n\n"
            "> Captured with `/wiki-save-answer`.\n\n"
            + new_section
        )
    path.write_text(content, encoding="utf-8")

    rel = f"queries/{safe}.md"
    store.append_wiki_log_line("wiki-save-answer", rel, when=when)
    git = store.git
    if git.is_initialized():
        git.auto_commit(f"wiki-save-answer: {safe}")

    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=f"Saved to `wiki/{rel}`.",
        metadata=dict(msg.metadata or {}),
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = [
        "🐈 nanobot commands:",
        "/new — Start a new conversation",
        "/stop — Stop the current task",
        "/restart — Restart the bot",
        "/status — Show bot status",
        "/dream — Manually trigger Dream consolidation",
        "/dream-log — Show what the last Dream changed",
        "/dream-restore — Revert memory to a previous state",
        "/wiki-archive — Write the current session to wiki and replace session context with the index",
        "/wiki-ingest — Import text from raw/sources/ into wiki (optional `/wiki-ingest <keyword>` path filter)",
        "/wiki-lint — Report broken [[wikilinks]] and orphan pages in wiki/",
        "/wiki-save-answer — Save the last assistant reply under wiki/queries/ (optional `/wiki-save-answer <slug>`)",
        "/help — Show available commands",
    ]
    return "\n".join(lines)


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.priority("/stop", cmd_stop)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/status", cmd_status)
    router.exact("/dream", cmd_dream)
    router.exact("/dream-log", cmd_dream_log)
    router.prefix("/dream-log ", cmd_dream_log)
    router.exact("/dream-restore", cmd_dream_restore)
    router.prefix("/dream-restore ", cmd_dream_restore)
    router.exact("/wiki-archive", cmd_wiki_archive)
    router.exact("/wiki-ingest", cmd_wiki_ingest)
    router.prefix("/wiki-ingest ", cmd_wiki_ingest)
    router.exact("/wiki-lint", cmd_wiki_lint)
    router.exact("/wiki-save-answer", cmd_wiki_save_answer)
    router.prefix("/wiki-save-answer ", cmd_wiki_save_answer)
    router.exact("/help", cmd_help)

"""Wiki automation: fingerprints, scheduled ingest/lint, optional lint after wiki writes."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.llm_wiki.lint import format_wiki_lint_message, run_wiki_lint
from nanobot.llm_wiki.raw import list_raw_source_files

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop

_STATE_FILENAME = "wiki_automation.json"


def wiki_automation_state_path(workspace: Path) -> Path:
    return workspace / "memory" / _STATE_FILENAME


def compute_raw_fingerprint(workspace: Path) -> str:
    """Stable hash of raw text source paths + mtime + size (sorted)."""
    paths = list_raw_source_files(workspace)
    lines: list[str] = []
    for rel in paths:
        p = workspace / rel
        try:
            st = p.stat()
        except OSError:
            continue
        lines.append(f"{rel}\t{st.st_mtime_ns}\t{st.st_size}\n")
    raw = "".join(lines).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _load_state(workspace: Path) -> dict[str, Any]:
    p = wiki_automation_state_path(workspace)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(workspace: Path, data: dict[str, Any]) -> None:
    p = wiki_automation_state_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def maybe_lint_after_wiki_write(
    store: MemoryStore,
    *,
    enabled: bool,
    source: str = "after-write",
) -> None:
    """Run wiki lint synchronously; append ``wiki/log.md`` only when there are issues."""
    if not enabled:
        return
    report = run_wiki_lint(store.workspace)
    n_dead = len(report.dead_links)
    n_orphan = len(report.orphan_pages)
    if n_dead == 0 and n_orphan == 0:
        logger.debug("wiki lint ({}): clean", source)
        return
    summary = f"{n_dead} dead link(s), {n_orphan} orphan(s)"
    store.append_wiki_log_line(f"auto-wiki-lint-{source}", summary)
    logger.info("wiki lint ({}): {}", source, summary)


async def tick_wiki_automation(
    loop: AgentLoop,
    *,
    ingest_interval_minutes: float | None,
    lint_interval_minutes: float | None,
) -> None:
    """One scheduler tick: optional auto-ingest when raw changes, optional periodic lint."""
    ws = loop.workspace
    state = _load_state(ws)
    now_m = time.monotonic()
    now_utc = datetime.now(timezone.utc).isoformat()

    fp = compute_raw_fingerprint(ws)
    stored_fp = str(state.get("raw_fingerprint") or "")

    # Baseline periodic lint timer so the first run waits a full interval after gateway start.
    if (
        lint_interval_minutes is not None
        and lint_interval_minutes > 0
        and "last_auto_lint_monotonic" not in state
    ):
        state["last_auto_lint_monotonic"] = now_m
        _save_state(ws, state)

    # --- auto ingest when fingerprint changed and cooldown elapsed ---
    if ingest_interval_minutes is not None and ingest_interval_minutes > 0:
        last_ingest_mono = float(state.get("last_auto_ingest_monotonic") or 0.0)
        cooldown_s = max(60.0, float(ingest_interval_minutes) * 60.0)
        cooldown_elapsed = last_ingest_mono <= 0 or (now_m - last_ingest_mono) >= cooldown_s
        if fp != stored_fp and cooldown_elapsed:
            from nanobot.command.wiki_ingest import run_wiki_ingest

            logger.info("Auto wiki-ingest: raw fingerprint changed, running ingest")
            result = await run_wiki_ingest(loop, workspace=ws, path_filter="")
            state["last_auto_ingest_monotonic"] = now_m
            state["last_auto_wiki_ingest_utc"] = now_utc
            if result.ok and result.called_model:
                state["raw_fingerprint"] = fp
                _save_state(ws, state)
                if getattr(loop, "auto_wiki_lint_after_wiki_write", False):
                    maybe_lint_after_wiki_write(
                        loop.consolidator.store,
                        enabled=True,
                        source="auto-ingest",
                    )
            elif result.ok and not result.called_model:
                state["raw_fingerprint"] = fp
                _save_state(ws, state)
            elif "did not return any writable" in result.message:
                # Nothing to distill — advance fingerprint to avoid tight retry loops
                state["raw_fingerprint"] = fp
                _save_state(ws, state)
            else:
                logger.warning("Auto wiki-ingest failed: {}", result.message)
                _save_state(ws, state)

    # --- periodic lint ---
    if lint_interval_minutes is not None and lint_interval_minutes > 0:
        last_lint_mono = float(state.get("last_auto_lint_monotonic") or 0.0)
        lint_cooldown_s = max(60.0, float(lint_interval_minutes) * 60.0)
        if last_lint_mono > 0 and (now_m - last_lint_mono) >= lint_cooldown_s:
            report = run_wiki_lint(ws)
            state["last_auto_lint_monotonic"] = now_m
            state["last_auto_wiki_lint_utc"] = now_utc
            _save_state(ws, state)
            n_dead = len(report.dead_links)
            n_orphan = len(report.orphan_pages)
            if n_dead or n_orphan:
                logger.info(
                    "Scheduled wiki-lint: {}",
                    format_wiki_lint_message(report, max_lines=10).replace("\n", " ")[:200],
                )
                loop.consolidator.store.append_wiki_log_line(
                    "auto-wiki-lint-scheduled",
                    f"{n_dead} dead link(s), {n_orphan} orphan(s)",
                )
            else:
                logger.debug("Scheduled wiki-lint: no issues")

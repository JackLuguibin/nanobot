"""JSONL token usage recording for LLM completions.

Concurrency model (per process):

- **Coroutines**: A single ``asyncio.Lock`` per JSONL file path serializes appends
  within one event loop.
- **Threads**: The lock registry is guarded by a ``threading.Lock`` so concurrent
  first-time lookups cannot create duplicate ``asyncio.Lock`` objects for the same
  path. Callbacks should run on the same event loop that owns the provider (typical
  for nanobot).
- **Processes**: Each process has its own ``asyncio.Lock`` table. On POSIX,
  ``fcntl.flock`` on the open file coordinates writers across processes; on Windows
  where ``fcntl`` is unavailable, append is best-effort (small JSON lines are often
  atomic, but concurrent multi-process writers are not fully serialized).
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanobot.providers.base import LLMCompletionCallback, LLMProvider, LLMResponse

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment, unused-ignore]

_jsonl_path_lock_registry: dict[str, asyncio.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for_usage_jsonl_path(path: Path) -> asyncio.Lock:
    key = str(path.resolve())
    with _registry_lock:
        if key not in _jsonl_path_lock_registry:
            _jsonl_path_lock_registry[key] = asyncio.Lock()
        return _jsonl_path_lock_registry[key]


def make_token_usage_jsonl_handler(usage_dir: Path | str) -> LLMCompletionCallback:
    """Build an async callback that appends one JSON line per successful LLM completion."""

    resolved_dir = Path(usage_dir).expanduser().resolve()

    async def on_llm_completion(response: LLMResponse, request_meta: dict[str, Any]) -> None:
        if response.finish_reason == "error":
            return
        model = str(request_meta.get("model", ""))
        payload: dict[str, Any] = {
            "event": "llm_call",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model.strip(),
            "finish_reason": response.finish_reason,
        }
        payload.update(response.usage or {})
        line = json.dumps(payload, ensure_ascii=False)
        date_str = datetime.now(timezone.utc).date().isoformat()
        path = resolved_dir / f"token_usage_{date_str}.jsonl"
        lock = _lock_for_usage_jsonl_path(path)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX) if fcntl else None
                try:
                    handle.write(line + "\n")
                    handle.flush()
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN) if fcntl else None

        async with lock:
            await asyncio.to_thread(_write)

    return on_llm_completion


def attach_token_usage_jsonl(provider: LLMProvider, workspace: Path | str) -> LLMCompletionCallback:
    """Register JSONL logging on *provider* for each successful LLM completion."""

    root = Path(workspace).expanduser().resolve()
    handler = make_token_usage_jsonl_handler(root / "usage")
    provider.add_on_completion(handler)
    return handler

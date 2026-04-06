"""Concurrency tests for JSONL token usage recording (async, threads, processes)."""

from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nanobot.providers.base import LLMResponse
from nanobot.utils.usage import (
    _lock_for_usage_jsonl_path,
    make_token_usage_jsonl_handler,
)


def _process_write_one_completion(usage_dir: str, completion_tokens: int) -> None:
    """Run in a child process: one handler invocation writing a single JSONL line."""
    import asyncio
    from pathlib import Path

    from nanobot.providers.base import LLMResponse
    from nanobot.utils.usage import make_token_usage_jsonl_handler

    handler = make_token_usage_jsonl_handler(Path(usage_dir))

    async def _run() -> None:
        await handler(
            LLMResponse(
                content="x",
                finish_reason="stop",
                usage={"completion_tokens": completion_tokens},
            ),
            {"model": "mp-stress"},
        )

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_lock_registry_single_asyncio_lock_per_resolved_path(tmp_path: Path) -> None:
    """Concurrent lookups must not install two different locks for the same file path."""
    log_path = tmp_path / "token_usage_2099-01-01.jsonl"

    async def _lookup() -> asyncio.Lock:
        return _lock_for_usage_jsonl_path(log_path)

    locks = await asyncio.gather(*(_lookup() for _ in range(64)))
    first = locks[0]
    assert all(lock is first for lock in locks)


@pytest.mark.asyncio
async def test_many_concurrent_async_writes_all_lines_are_valid_json(
    tmp_path: Path,
) -> None:
    """Many coroutines appending the same daily file: each line must be one JSON object."""
    usage_dir = tmp_path / "usage"
    handler = make_token_usage_jsonl_handler(usage_dir)

    async def _one_call(index: int) -> None:
        await handler(
            LLMResponse(
                content="ok",
                finish_reason="stop",
                usage={"prompt_tokens": index, "completion_tokens": index + 1},
            ),
            {"model": f"model-{index}"},
        )

    await asyncio.gather(*(_one_call(index) for index in range(200)))

    date_str = datetime.now(timezone.utc).date().isoformat()
    log_path = usage_dir / f"token_usage_{date_str}.jsonl"
    raw = log_path.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    assert len(lines) == 200
    prompt_values: set[int] = set()
    for line in lines:
        row = json.loads(line)
        assert row["event"] == "llm_call"
        assert row["finish_reason"] == "stop"
        assert isinstance(row["prompt_tokens"], int)
        prompt_values.add(row["prompt_tokens"])
    assert prompt_values == set(range(200))


def test_thread_pool_concurrent_first_touch_same_path_unifies_lock(tmp_path: Path) -> None:
    """Threads racing on first _lock_for_usage_jsonl_path must still share one asyncio.Lock."""

    log_path = tmp_path / "token_usage_2099-06-15.jsonl"

    def _sync_lookup() -> asyncio.Lock:
        return _lock_for_usage_jsonl_path(log_path)

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(_sync_lookup) for _ in range(32)]
        locks = [future.result() for future in as_completed(futures)]

    assert len({id(lock) for lock in locks}) == 1


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="fcntl unavailable; cross-process file locking not implemented for Windows",
)
def test_multiprocess_writes_yield_distinct_valid_json_lines(tmp_path: Path) -> None:
    """POSIX: fcntl + per-process asyncio lock; lines must not be interleaved mid-record."""
    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    token_values = list(range(24))

    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(_process_write_one_completion, str(usage_dir), token)
            for token in token_values
        ]
        for future in futures:
            future.result()

    date_str = datetime.now(timezone.utc).date().isoformat()
    log_path = usage_dir / f"token_usage_{date_str}.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(token_values)
    seen_tokens: set[int] = set()
    for line in lines:
        row = json.loads(line)
        assert row["event"] == "llm_call"
        seen_tokens.add(row["completion_tokens"])
    assert seen_tokens == set(token_values)


@pytest.mark.asyncio
async def test_error_finish_reason_skips_write_no_empty_corruption(tmp_path: Path) -> None:
    """Skipped writes should not leave partial lines (regression guard)."""
    usage_dir = tmp_path / "usage"
    handler = make_token_usage_jsonl_handler(usage_dir)

    await handler(
        LLMResponse(content=None, finish_reason="error", usage={}),
        {"model": "x"},
    )

    date_str = datetime.now(timezone.utc).date().isoformat()
    log_path = usage_dir / f"token_usage_{date_str}.jsonl"
    assert not log_path.exists()


@pytest.mark.asyncio
async def test_fcntl_write_path_used_when_fcntl_available(tmp_path: Path) -> None:
    """Ensure the fcntl branch runs on POSIX (mock fcntl to count lock calls)."""
    usage_dir = tmp_path / "usage"
    handler = make_token_usage_jsonl_handler(usage_dir)

    lock_calls: list[str] = []

    class _FakeFcntl:
        LOCK_EX = 2
        LOCK_UN = 8

        def flock(self, fd: int, op: int) -> None:  # noqa: ARG002
            lock_calls.append("EX" if op == self.LOCK_EX else "UN")

    fake = _FakeFcntl()
    with patch("nanobot.utils.usage.fcntl", fake):
        await handler(
            LLMResponse(
                content="ok",
                finish_reason="stop",
                usage={"prompt_tokens": 1, "completion_tokens": 2},
            ),
            {"model": "mock-fcntl"},
        )

    assert "EX" in lock_calls and "UN" in lock_calls

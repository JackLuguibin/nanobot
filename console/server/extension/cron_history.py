"""Cron execution history extension.

记录每次 Cron 任务执行：时间、状态、耗时。
持久化到 {config_dir}/cron/history.json，每个 job 保留最近 N 次记录。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MAX_HISTORY_PER_JOB = 20


def _get_history_path(bot_id: str) -> Path:
    """获取 cron history 文件路径。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "cron" / "history.json"
    except Exception:
        pass
    return Path.home() / ".nanobot" / "bots" / bot_id / "cron" / "history.json"


def _load_history(bot_id: str) -> dict[str, list[dict[str, Any]]]:
    """加载执行历史。结构: { job_id: [ { run_at_ms, status, duration_ms, error }, ... ] }"""
    path = _get_history_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_history(bot_id: str, data: dict[str, list[dict[str, Any]]]) -> None:
    """保存执行历史。"""
    path = _get_history_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def append_cron_run(
    bot_id: str,
    job_id: str,
    job_name: str,
    run_at_ms: int,
    status: str,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """追加一次 Cron 执行记录。"""
    data = _load_history(bot_id)
    if job_id not in data:
        data[job_id] = []
    entry = {
        "job_id": job_id,
        "job_name": job_name,
        "run_at_ms": run_at_ms,
        "status": status,
        "duration_ms": duration_ms,
        "error": error,
    }
    data[job_id].append(entry)
    data[job_id] = data[job_id][-_MAX_HISTORY_PER_JOB:]
    _save_history(bot_id, data)


def get_cron_history(bot_id: str, job_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """获取执行历史。若指定 job_id 则只返回该 job 的历史。"""
    data = _load_history(bot_id)
    if job_id:
        return {job_id: data.get(job_id, [])}
    return data

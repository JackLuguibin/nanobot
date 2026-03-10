"""Activity log persistence for console.

将 tool_call 等事件持久化到 {config_dir}/activity.json。
支持按日期轮转，保留最近 N 条。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_MAX_ACTIVITY_ENTRIES = 5000


def _get_activity_path(bot_id: str) -> Path:
    """获取 activity 文件路径。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "activity.json"
    except Exception:
        pass
    return Path.home() / ".nanobot" / "bots" / bot_id / "activity.json"


def _load_activity(bot_id: str) -> list[dict[str, Any]]:
    """加载 activity 列表。"""
    path = _get_activity_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", [])
    except Exception:
        return []


def _save_activity(bot_id: str, entries: list[dict[str, Any]]) -> None:
    """保存 activity 列表。"""
    path = _get_activity_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, indent=2, ensure_ascii=False)


def append_activity(bot_id: str, activity_type: str, data: dict[str, Any]) -> None:
    """追加一条 activity 记录。"""
    entries = _load_activity(bot_id)
    entry = {
        "id": str(uuid.uuid4())[:8],
        "type": activity_type,
        "timestamp": time.time(),
        "data": data,
    }
    entries.append(entry)
    entries = entries[-_MAX_ACTIVITY_ENTRIES:]
    _save_activity(bot_id, entries)


def get_activity(
    bot_id: str,
    limit: int = 100,
    activity_type: str | None = None,
) -> list[dict[str, Any]]:
    """获取 activity 列表，按时间倒序。"""
    entries = _load_activity(bot_id)
    if activity_type:
        entries = [e for e in entries if e.get("type") == activity_type]
    return entries[-limit:][::-1]


def wrap_tool_registry_for_logging(registry, bot_id: str):
    """包装 ToolRegistry，在 execute 时记录到 state 和 activity。"""
    import asyncio

    from console.server.api.state import get_state

    _original_execute = registry.execute

    async def _logged_execute(name: str, params: dict[str, Any]) -> str:
        start = time.time()
        tool_id = str(uuid.uuid4())[:8]
        result = await _original_execute(name, params)
        duration_ms = (time.time() - start) * 1000
        is_error = isinstance(result, str) and result.startswith("Error")
        status = "error" if is_error else "success"
        log_entry = {
            "id": tool_id,
            "tool_name": name,
            "arguments": params,
            "result": (result[:500] + "...") if len(str(result)) > 500 else result,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        }
        try:
            state = get_state(bot_id)
            state.add_tool_call_log(log_entry)
        except Exception:
            pass
        append_activity(
            bot_id,
            "tool_call",
            {
                "tool_name": name,
                "arguments": params,
                "result": log_entry["result"],
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        return result

    registry.execute = _logged_execute
    return registry

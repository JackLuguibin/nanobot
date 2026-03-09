"""Token usage tracking extension for console.

包装 LLM provider，在每次 chat 调用后累积 token 使用量，持久化到各 bot 目录下的 JSON 文件，供 Dashboard 展示。
不修改 nanobot 核心代码，仅在 extension 层扩展。
每个 bot 的 usage 存储在自身 config 目录下，不放在公共区域。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider, LLMResponse


def _get_usage_file_path(bot_id: str) -> Path:
    """获取指定 bot 的 usage 存储文件路径，位于该 bot 的 config 目录下。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "usage.json"
    except Exception:
        pass
    return Path.home() / ".nanobot" / "bots" / bot_id / "usage.json"


def _load_usage_data(bot_id: str) -> dict[str, dict[str, int]]:
    """从该 bot 的 JSON 文件加载使用量数据。结构: {date: {prompt_tokens, completion_tokens, total_tokens}}"""
    path = _get_usage_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage_data(bot_id: str, data: dict[str, dict[str, int]]) -> None:
    """保存使用量数据到该 bot 的 JSON 文件。"""
    path = _get_usage_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _add_usage(bot_id: str, usage: dict[str, int]) -> None:
    """累积 token 使用量并持久化到该 bot 的 JSON 文件。"""
    if not usage:
        return
    data = _load_usage_data(bot_id)
    today = date.today().isoformat()
    if today not in data:
        data[today] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        data[today][k] = data[today].get(k, 0) + usage.get(k, 0)
    _save_usage_data(bot_id, data)


def get_usage_today(bot_id: str) -> dict[str, int]:
    """获取指定 bot 当日 token 使用量。"""
    data = _load_usage_data(bot_id)
    today = date.today().isoformat()
    return dict(data.get(today, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}))


def get_usage_history(bot_id: str, days: int = 14) -> list[dict[str, Any]]:
    """获取指定 bot 最近 N 天的每日 token 使用量，用于柱状图展示。
    返回: [{"date": "2025-03-01", "total_tokens": 1000, "prompt_tokens": 600, "completion_tokens": 400}, ...]
    按日期升序排列。
    """
    data = _load_usage_data(bot_id)
    result = []
    for i in range(days - 1, -1, -1):
        d = date.today() - timedelta(days=i)
        day_str = d.isoformat()
        row = data.get(day_str, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        result.append({
            "date": day_str,
            "total_tokens": row.get("total_tokens", 0),
            "prompt_tokens": row.get("prompt_tokens", 0),
            "completion_tokens": row.get("completion_tokens", 0),
        })
    return result


class UsageTrackingProvider:
    """包装任意 LLMProvider，在 chat 返回后累积 usage 并持久化到该 bot 的 JSON 文件。"""

    def __init__(self, provider: "LLMProvider", bot_id: str) -> None:
        self._provider = provider
        self._bot_id = bot_id

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> "LLMResponse":
        response = await self._provider.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        usage = getattr(response, "usage", None) or {}
        _add_usage(self._bot_id, usage)
        return response

    def get_default_model(self) -> str:
        return self._provider.get_default_model()

    def __getattr__(self, name: str) -> Any:
        """转发其他属性到底层 provider。"""
        return getattr(self._provider, name)

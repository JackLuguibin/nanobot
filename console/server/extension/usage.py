"""Token usage tracking extension for console.

包装 LLM provider，在每次 chat 调用后累积 token 使用量，持久化到各 bot 目录下的 JSON 文件，供 Dashboard 展示。
按模型分别记录使用量，支持多模型用量统计。
每个 bot 的 usage 存储在自身 config 目录下，不放在公共区域。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider, LLMResponse

# 新格式: {date: {model: {prompt_tokens, completion_tokens, total_tokens}}}
# 旧格式: {date: {prompt_tokens, completion_tokens, total_tokens}} -> 迁移为 model="unknown"
_TOKEN_KEYS = frozenset(("prompt_tokens", "completion_tokens", "total_tokens"))


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


def _is_legacy_day_data(day_data: dict[str, Any]) -> bool:
    """判断是否为旧格式：顶层直接是 prompt_tokens/completion_tokens/total_tokens。"""
    return bool(day_data and _TOKEN_KEYS & set(day_data.keys()))


def _normalize_usage_data(data: dict[str, Any]) -> dict[str, dict[str, dict[str, int]]]:
    """将加载的数据规范为新格式 {date: {model: {prompt_tokens, completion_tokens, total_tokens}}}。"""
    result: dict[str, dict[str, dict[str, int]]] = {}
    for day_str, day_data in data.items():
        if not isinstance(day_data, dict):
            continue
        if _is_legacy_day_data(day_data):
            # 旧格式：迁移到 model="unknown"
            result[day_str] = {
                "unknown": {
                    "prompt_tokens": day_data.get("prompt_tokens", 0),
                    "completion_tokens": day_data.get("completion_tokens", 0),
                    "total_tokens": day_data.get("total_tokens", 0),
                }
            }
        else:
            # 新格式：按模型
            result[day_str] = {}
            for model, usage in day_data.items():
                if isinstance(usage, dict):
                    result[day_str][model] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }
    return result


def _load_usage_data(bot_id: str) -> dict[str, dict[str, dict[str, int]]]:
    """从该 bot 的 JSON 文件加载使用量数据。
    结构: {date: {model: {prompt_tokens, completion_tokens, total_tokens}}}
    """
    path = _get_usage_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return _normalize_usage_data(raw)
    except Exception:
        return {}


def _save_usage_data(bot_id: str, data: dict[str, dict[str, dict[str, int]]]) -> None:
    """保存使用量数据到该 bot 的 JSON 文件。"""
    path = _get_usage_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _add_usage(bot_id: str, usage: dict[str, int], model: str) -> None:
    """按模型累积 token 使用量并持久化到该 bot 的 JSON 文件。"""
    if not usage:
        return
    model = model or "unknown"
    data = _load_usage_data(bot_id)
    today = date.today().isoformat()
    if today not in data:
        data[today] = {}
    if model not in data[today]:
        data[today][model] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        data[today][model][k] = data[today][model].get(k, 0) + usage.get(k, 0)
    _save_usage_data(bot_id, data)


def _aggregate_by_model(by_model: dict[str, dict[str, int]]) -> dict[str, int]:
    """将按模型的数据聚合成总量。"""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for m in by_model.values():
        for k in _TOKEN_KEYS:
            total[k] = total.get(k, 0) + m.get(k, 0)
    return total


def get_usage_today(bot_id: str) -> dict[str, Any]:
    """获取指定 bot 当日 token 使用量。
    返回: {
        "total_tokens": int, "prompt_tokens": int, "completion_tokens": int,  # 总量，兼容旧接口
        "by_model": { model: { prompt_tokens, completion_tokens, total_tokens }, ... }
    }
    """
    data = _load_usage_data(bot_id)
    today = date.today().isoformat()
    by_model = dict(data.get(today, {}))
    total = _aggregate_by_model(by_model)
    return {
        "total_tokens": total.get("total_tokens", 0),
        "prompt_tokens": total.get("prompt_tokens", 0),
        "completion_tokens": total.get("completion_tokens", 0),
        "by_model": by_model,
    }


def get_usage_history(bot_id: str, days: int = 14) -> list[dict[str, Any]]:
    """获取指定 bot 最近 N 天的每日 token 使用量，用于柱状图展示。
    返回: [
        {"date": "2025-03-01", "total_tokens": 1000, "prompt_tokens": 600, "completion_tokens": 400, "by_model": {...}},
        ...
    ]
    按日期升序排列。每日总量为各模型之和。
    """
    data = _load_usage_data(bot_id)
    result = []
    for i in range(days - 1, -1, -1):
        d = date.today() - timedelta(days=i)
        day_str = d.isoformat()
        by_model = dict(data.get(day_str, {}))
        total = _aggregate_by_model(by_model)
        result.append({
            "date": day_str,
            "total_tokens": total.get("total_tokens", 0),
            "prompt_tokens": total.get("prompt_tokens", 0),
            "completion_tokens": total.get("completion_tokens", 0),
            "by_model": by_model,
        })
    return result


class UsageTrackingProvider:
    """包装任意 LLMProvider，在 chat 返回后按模型累积 usage 并持久化到该 bot 的 JSON 文件。"""

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
        model_name = model or self._provider.get_default_model()
        _add_usage(self._bot_id, usage, model_name)
        return response

    def get_default_model(self) -> str:
        return self._provider.get_default_model()

    def __getattr__(self, name: str) -> Any:
        """转发其他属性到底层 provider。"""
        return getattr(self._provider, name)

"""Token usage tracking extension for console.

包装 LLM provider，在每次 chat 调用后累积 token 使用量，持久化到各 bot 目录下的 JSON 文件，供 Dashboard 展示。
按模型分别记录使用量，支持多模型用量统计。
每个 bot 的 usage 存储在自身 config 目录下，不放在公共区域。
支持成本换算：模型单价（每百万 token）可配置，支持用户自定义。
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider, LLMResponse

# 新格式: {date: {model: {prompt_tokens, completion_tokens, total_tokens}}}
# 旧格式: {date: {prompt_tokens, completion_tokens, total_tokens}} -> 迁移为 model="unknown"
_TOKEN_KEYS = frozenset(("prompt_tokens", "completion_tokens", "total_tokens"))

# 默认模型单价（美元/百万 token）：input, output
# 参考 OpenAI/Azure 2024 年定价，未知模型使用 fallback
_DEFAULT_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4-turbo": (10.0, 30.0),
    "gpt-4": (30.0, 60.0),
    "gpt-3.5-turbo": (0.5, 1.5),
    "o1": (15.0, 60.0),
    "o1-mini": (3.0, 12.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-sonnet": (3.0, 15.0),
    "claude-3-haiku": (0.25, 1.25),
    "gemini-1.5-pro": (1.25, 5.0),
    "gemini-1.5-flash": (0.075, 0.3),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-coder": (0.14, 0.28),
    "unknown": (0.5, 1.5),
}


def _get_model_prices(bot_id: str | None = None) -> dict[str, tuple[float, float]]:
    """获取模型单价。优先从环境变量 NANOBOT_MODEL_PRICES（JSON）或 config 读取，否则用默认值。"""
    prices = dict(_DEFAULT_MODEL_PRICES)

    # 环境变量: {"gpt-4o": [2.5, 10], ...}
    env_prices = os.environ.get("NANOBOT_MODEL_PRICES")
    if env_prices:
        try:
            custom = json.loads(env_prices)
            for k, v in custom.items():
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    prices[k] = (float(v[0]), float(v[1]))
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Failed to parse NANOBOT_MODEL_PRICES env var: {}", e)

    # Config: console.model_prices 或 providers.*.model_prices
    try:
        from console.server.bot_registry import get_registry

        registry = get_registry()
        bot = registry.get_bot(bot_id) if bot_id else None
        if not bot and registry.default_bot_id:
            bot = registry.get_bot(registry.default_bot_id)
        if bot and bot.config_path:
            config_path = Path(bot.config_path)
            if config_path.exists():
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                custom = cfg.get("console", {}).get("model_prices") or cfg.get("model_prices")
                if isinstance(custom, dict):
                    for k, v in custom.items():
                        if isinstance(v, (list, tuple)) and len(v) >= 2:
                            prices[k] = (float(v[0]), float(v[1]))
    except Exception as e:
        logger.debug("Failed to get model prices from config: {}", e)

    return prices


def _calc_cost(
    by_model: dict[str, dict[str, int]], prices: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    """根据 token 用量和单价计算成本。返回 { total_usd, by_model: { model: usd } }"""
    total = 0.0
    by_model_cost: dict[str, float] = {}
    for model, usage in by_model.items():
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        # 模型名可能带后缀，尝试匹配前缀
        price_input, price_output = prices.get(model) or _find_model_price(model, prices)
        cost = (prompt_tokens / 1_000_000) * price_input + (
            completion_tokens / 1_000_000
        ) * price_output
        by_model_cost[model] = round(cost, 6)
        total += cost
    return {"total_usd": round(total, 6), "by_model": by_model_cost}


def _find_model_price(model: str, prices: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """按模型名前缀匹配单价。"""
    for key, val in prices.items():
        if model == key or model.startswith(key + "-") or model.startswith(key + "."):
            return val
    return prices.get("unknown", (0.5, 1.5))


def _get_usage_file_path(bot_id: str) -> Path:
    """获取指定 bot 的 usage 存储文件路径，位于该 bot 的 config 目录下。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "usage.json"
    except Exception as e:
        logger.debug("Failed to get usage file path for bot '{}': {}", bot_id, e)
    return Path.home() / ".nanobot" / "bots" / bot_id / "usage.json"


def _is_legacy_day_data(day_data: dict[str, Any]) -> bool:
    """判断是否为旧格式：顶层直接是 prompt_tokens/completion_tokens/total_tokens。"""
    return bool(day_data and _TOKEN_KEYS & set(day_data.keys()))


def _safe_int(v: Any, default: int = 0) -> int:
    """将可能为 None 或非数值的值转为 int，避免 None 参与运算或比较。"""
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _normalize_usage_data(data: dict[str, Any]) -> dict[str, dict[str, dict[str, int]]]:
    """将加载的数据规范为新格式 {date: {model: {prompt_tokens, completion_tokens, total_tokens}}}。"""
    result: dict[str, dict[str, dict[str, int]]] = {}
    for day_str, day_data in data.items():
        if not isinstance(day_data, dict):
            continue
        if _is_legacy_day_data(day_data):
            # 旧格式：迁移到 model="unknown"，None 规整为 0
            result[day_str] = {
                "unknown": {
                    "prompt_tokens": _safe_int(day_data.get("prompt_tokens"), 0),
                    "completion_tokens": _safe_int(day_data.get("completion_tokens"), 0),
                    "total_tokens": _safe_int(day_data.get("total_tokens"), 0),
                }
            }
        else:
            # 新格式：按模型，None 规整为 0
            result[day_str] = {}
            for model, usage in day_data.items():
                if isinstance(usage, dict):
                    result[day_str][model] = {
                        "prompt_tokens": _safe_int(usage.get("prompt_tokens"), 0),
                        "completion_tokens": _safe_int(usage.get("completion_tokens"), 0),
                        "total_tokens": _safe_int(usage.get("total_tokens"), 0),
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
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Failed to load usage data for bot '{}': {}", bot_id, e)
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
        prev = _safe_int(data[today][model].get(k), 0)
        inc = _safe_int(usage.get(k), 0)
        data[today][model][k] = prev + inc
    _save_usage_data(bot_id, data)


def _aggregate_by_model(by_model: dict[str, dict[str, int]]) -> dict[str, int]:
    """将按模型的数据聚合成总量。"""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for m in by_model.values():
        for k in _TOKEN_KEYS:
            total[k] = total.get(k, 0) + _safe_int(m.get(k), 0)
    return total


def get_usage_today(bot_id: str) -> dict[str, Any]:
    """获取指定 bot 当日 token 使用量。
    返回: {
        "total_tokens": int, "prompt_tokens": int, "completion_tokens": int,  # 总量，兼容旧接口
        "by_model": { model: { prompt_tokens, completion_tokens, total_tokens }, ... },
        "cost_usd": float, "cost_by_model": { model: usd }  # 成本
    }
    """
    data = _load_usage_data(bot_id)
    today = date.today().isoformat()
    by_model = dict(data.get(today, {}))
    total = _aggregate_by_model(by_model)
    prices = _get_model_prices(bot_id)
    cost_info = _calc_cost(by_model, prices)
    return {
        "total_tokens": total.get("total_tokens", 0),
        "prompt_tokens": total.get("prompt_tokens", 0),
        "completion_tokens": total.get("completion_tokens", 0),
        "by_model": by_model,
        "cost_usd": cost_info["total_usd"],
        "cost_by_model": cost_info["by_model"],
    }


def get_usage_cost(bot_id: str, target_date: str | date | None = None) -> dict[str, Any]:
    """获取指定 bot 某日成本。
    返回: { "date": str, "total_usd": float, "by_model": { model: usd } }
    """
    if target_date is None:
        target_date = date.today()
    if isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    day_str = target_date.isoformat()
    data = _load_usage_data(bot_id)
    by_model = dict(data.get(day_str, {}))
    prices = _get_model_prices(bot_id)
    cost_info = _calc_cost(by_model, prices)
    return {
        "date": day_str,
        "total_usd": cost_info["total_usd"],
        "by_model": cost_info["by_model"],
    }


def get_usage_history(bot_id: str, days: int = 14) -> list[dict[str, Any]]:
    """获取指定 bot 最近 N 天的每日 token 使用量，用于柱状图展示。
    返回: [
        {"date": "2025-03-01", "total_tokens": 1000, "prompt_tokens": 600, "completion_tokens": 400,
         "by_model": {...}, "cost_usd": 0.05, "cost_by_model": {...}},
        ...
    ]
    按日期升序排列。每日总量为各模型之和。
    """
    data = _load_usage_data(bot_id)
    prices = _get_model_prices(bot_id)
    result = []
    for i in range(days - 1, -1, -1):
        d = date.today() - timedelta(days=i)
        day_str = d.isoformat()
        by_model = dict(data.get(day_str, {}))
        total = _aggregate_by_model(by_model)
        cost_info = _calc_cost(by_model, prices)
        result.append(
            {
                "date": day_str,
                "total_tokens": total.get("total_tokens", 0),
                "prompt_tokens": total.get("prompt_tokens", 0),
                "completion_tokens": total.get("completion_tokens", 0),
                "by_model": by_model,
                "cost_usd": cost_info["total_usd"],
                "cost_by_model": cost_info["by_model"],
            }
        )
    return result


def _usage_to_dict(usage: Any) -> dict[str, int]:
    """将 usage 规范为 dict，兼容 LLMResponse.usage 或对象形式。"""
    if not usage:
        return {}
    if isinstance(usage, dict):
        return {k: int(usage[k]) for k in _TOKEN_KEYS if k in usage and usage[k] is not None}
    # 兼容具名元组或 dataclass
    return {
        k: int(getattr(usage, k, 0) or 0)
        for k in _TOKEN_KEYS
        if hasattr(usage, k)
    }


class UsageTrackingProvider:
    """包装任意 LLMProvider，在 chat/chat_with_retry 返回后按模型累积 usage 并持久化到该 bot 的 JSON 文件。"""

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
        tool_choice: str | dict[str, Any] | None = None,
    ) -> "LLMResponse":
        response = await self._provider.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        usage = _usage_to_dict(getattr(response, "usage", None))
        if usage:
            model_name = model or self._provider.get_default_model()
            _add_usage(self._bot_id, usage, model_name)
        return response

    async def chat_with_retry(self, *args: Any, **kwargs: Any) -> "LLMResponse":
        """调用底层 provider.chat_with_retry，返回后记录 token 使用量。用 *args/**kwargs 透传，避免把 None 当作显式参数导致底层出现 None 与 int 比较。"""
        response = await self._provider.chat_with_retry(*args, **kwargs)
        usage = _usage_to_dict(getattr(response, "usage", None))
        if usage:
            model_name = kwargs.get("model") or self._provider.get_default_model()
            _add_usage(self._bot_id, usage, model_name)
        return response

    def get_default_model(self) -> str:
        return self._provider.get_default_model()

    def __getattr__(self, name: str) -> Any:
        """转发其他属性到底层 provider。"""
        return getattr(self._provider, name)

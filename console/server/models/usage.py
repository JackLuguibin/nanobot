"""Usage / billing models."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class TokenUsageResponse(BaseModel):
    """当日 token 使用量与成本，与 extension.usage.get_usage_today 返回结构一致。"""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_by_model: dict[str, float] = Field(default_factory=dict)


class UsageHistoryItem(BaseModel):
    """Single day of token usage history."""

    date: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_by_model: dict[str, float] = Field(default_factory=dict)


class UsageCostResponse(BaseModel):
    """Cost response for GET /usage/cost."""

    date: Optional[date] = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)
    cost_usd: float = 0.0
    cost_by_model: dict[str, float] = Field(default_factory=dict)

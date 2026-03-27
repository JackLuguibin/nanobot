"""API routes for usage tracking."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from console.server.api.state import get_state
from console.server.models.usage import UsageHistoryItem, UsageCostResponse

router = APIRouter(prefix="/usage")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("/history", response_model=list[UsageHistoryItem])
async def get_usage_history(
    bot_id: str | None = Query(None),
    days: int = Query(14, ge=1, le=90),
) -> list[UsageHistoryItem]:
    """Get daily token usage history for the chart (includes cost_usd, cost_by_model)."""
    from console.server.extension.usage import get_usage_history as _get_usage_history

    state = _resolve_state(bot_id)
    raw_list = _get_usage_history(state.bot_id, days=days)
    return [UsageHistoryItem(**item) for item in raw_list]


@router.get("/cost", response_model=UsageCostResponse)
async def get_usage_cost(
    bot_id: str | None = Query(None),
    date_str: str | None = Query(None, description="ISO date, e.g. 2025-03-10"),
) -> UsageCostResponse:
    """Get cost for a specific date (default: today)."""
    from datetime import date

    from console.server.extension.usage import get_usage_cost as _get_usage_cost

    state = _resolve_state(bot_id)
    target = date.fromisoformat(date_str) if date_str else None
    raw = _get_usage_cost(state.bot_id, target)
    return UsageCostResponse(**raw)

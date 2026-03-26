"""API routes for status, channels, tools and monitoring."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.models.base import ChannelStatus, MCPStatus, ToolCallLog
from console.server.models.system import StatusResponse
from console.server.models.status import ChannelUpdateRequest

router = APIRouter(prefix="/status")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("", response_model=StatusResponse)
async def get_status(bot_id: str | None = Query(None)) -> StatusResponse:
    """Get the overall bot status."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return StatusResponse(**status)


@router.get("/usage/history")
async def get_usage_history(
    bot_id: str | None = Query(None),
    days: int = Query(14, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Get daily token usage history for the chart (includes cost_usd, cost_by_model)."""
    from console.server.extension.usage import get_usage_history

    state = _resolve_state(bot_id)
    return get_usage_history(state.bot_id, days=days)


@router.get("/usage/cost")
async def get_usage_cost(
    bot_id: str | None = Query(None),
    date_str: str | None = Query(None, description="ISO date, e.g. 2025-03-10"),
) -> dict[str, Any]:
    """Get cost for a specific date (default: today)."""
    from datetime import date

    from console.server.extension.usage import get_usage_cost as _get_usage_cost

    state = _resolve_state(bot_id)
    target = date.fromisoformat(date_str) if date_str else None
    return _get_usage_cost(state.bot_id, target)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


@router.get("/channels", response_model=list[ChannelStatus])
async def get_channels(bot_id: str | None = Query(None)) -> list[ChannelStatus]:
    """Get all channels from config, merged with runtime status when available."""
    state = _resolve_state(bot_id)
    channels = await state.get_channels()
    return [ChannelStatus(**ch) for ch in channels]


@router.put("/channels/{name}")
async def update_channel(
    name: str,
    request: ChannelUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Update a channel's configuration."""
    state = _resolve_state(bot_id)
    try:
        return await state.update_channel(name, request.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/channels/{name}")
async def delete_channel(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Disable a channel (set enabled=False)."""
    state = _resolve_state(bot_id)
    ok = await state.delete_channel(name)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {name}")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


@router.get("/mcp", response_model=list[MCPStatus])
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


# ---------------------------------------------------------------------------
# Tool Call Logs
# ---------------------------------------------------------------------------


def _activity_to_tool_log(entry: dict) -> dict:
    """Convert activity entry to ToolCallLog format."""
    from datetime import datetime

    data = entry.get("data") or {}
    ts = entry.get("timestamp", 0)
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts)
        ts_str = dt.isoformat()
    else:
        ts_str = str(ts)
    return {
        "id": entry.get("id", ""),
        "tool_name": data.get("tool_name", ""),
        "arguments": data.get("arguments") or {},
        "result": data.get("result") or data.get("error"),
        "status": "success" if data.get("status") == "success" else "error",
        "duration_ms": data.get("duration_ms", 0),
        "timestamp": ts_str,
    }


@router.get("/tools/log", response_model=list[ToolCallLog])
async def get_tool_logs(
    limit: int = 50,
    tool_name: str | None = None,
    bot_id: str | None = Query(None),
) -> list[ToolCallLog]:
    """Get tool call logs (in-memory + persisted activity)."""
    state = _resolve_state(bot_id)
    logs = list(state.tool_call_logs)

    # Merge with persisted activity (for tool_call type)
    if state.bot_id != "_empty":
        try:
            from console.server.extension.activity import get_activity

            activity = get_activity(state.bot_id, limit=limit * 2, activity_type="tool_call")
            seen_ids = {log.get("id") for log in logs}
            for entry in activity:
                if entry.get("id") in seen_ids:
                    continue
                log = _activity_to_tool_log(entry)
                if tool_name and log.get("tool_name") != tool_name:
                    continue
                logs.append(log)
                seen_ids.add(entry.get("id"))
        except Exception as e:
            logger.debug("Failed to convert activity entry to tool log: {}", e)

    if tool_name:
        logs = [log for log in logs if log.get("tool_name") == tool_name]

    logs = sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]

    return [ToolCallLog(**log) for log in logs]

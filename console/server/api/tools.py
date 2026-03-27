"""API routes for tool call logs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.models.status import ToolCallLog

router = APIRouter(prefix="/tools")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


def _activity_to_tool_log(entry: dict) -> dict:
    """Convert activity entry to ToolCallLog format."""
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


@router.get("/log", response_model=list[ToolCallLog])
async def get_tool_logs(
    limit: int = 50,
    tool_name: str | None = None,
    bot_id: str | None = Query(None),
) -> list[ToolCallLog]:
    """Get tool call logs (in-memory + persisted activity)."""
    state = _resolve_state(bot_id)
    logs = list(state.tool_call_logs)

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

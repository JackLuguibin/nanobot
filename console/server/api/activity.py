"""API routes for activity feed."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from console.server.api.state import get_state
from console.server.models.activity import ActivityEntry, ActivityEntryType

router = APIRouter(prefix="/activity")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[ActivityEntry])
async def get_activity_feed(
    bot_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    activity_type: str | None = Query(
        None, description="Filter by activity type: message, tool_call, channel, session, error"
    ),
) -> list[ActivityEntry]:
    """Get activity feed with various event types."""
    state = _resolve_state(bot_id)

    if state.bot_id == "_empty":
        return []

    from console.server.extension.activity import get_activity as _get_activity

    activities = _get_activity(state.bot_id, limit=limit, activity_type=activity_type)

    result = []
    for entry in activities:
        ts = entry.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts)
        else:
            dt = None

        data = entry.get("data") or {}
        entry_type = entry.get("type", "unknown")

        title = ""
        description = ""

        if entry_type == "tool_call":
            title = f"Tool: {data.get('tool_name', 'unknown')}"
            description = f"Status: {data.get('status', 'unknown')}"
        elif entry_type == "message":
            title = "Message received"
            content = data.get("content", "")
            description = content[:100] + "..." if len(content) > 100 else content
        elif entry_type == "channel":
            title = f"Channel: {data.get('channel', 'unknown')}"
            description = data.get("event", "event")
        elif entry_type == "session":
            title = f"Session: {data.get('action', 'unknown')}"
            description = data.get("session_key", "")
        elif entry_type == "error":
            title = "Error occurred"
            description = data.get("error", "Unknown error")[:100]

        result.append(
            ActivityEntry(
                id=entry.get("id", ""),
                type=ActivityEntryType(entry_type) if entry_type in ActivityEntryType._value2member_map_ else ActivityEntryType.MESSAGE,
                title=title,
                description=description,
                timestamp=dt,
                metadata=data,
            )
        )

    return result

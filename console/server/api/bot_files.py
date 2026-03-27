"""API routes for bot profile files."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.workspace import (
    BotFileUpdateRequest,
    BotFileUpdateResponse,
    BotFilesResponse,
)

router = APIRouter(prefix="/bot-files")

BOT_FILE_KEYS: dict[str, str] = {
    "soul": "SOUL.md",
    "user": "USER.md",
    "heartbeat": "HEARTBEAT.md",
    "tools": "TOOLS.md",
    "agents": "AGENTS.md",
}


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


def _read_workspace_file(workspace: Path, filename: str) -> str:
    """Read a file from workspace, return empty string if not found."""
    path = workspace / filename
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


@router.get("", response_model=BotFilesResponse)
async def get_bot_files(bot_id: str | None = Query(None)) -> BotFilesResponse:
    """Get SOUL, USER, HEARTBEAT, TOOLS, AGENTS from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return BotFilesResponse(
        soul=_read_workspace_file(workspace, BOT_FILE_KEYS["soul"]),
        user=_read_workspace_file(workspace, BOT_FILE_KEYS["user"]),
        heartbeat=_read_workspace_file(workspace, BOT_FILE_KEYS["heartbeat"]),
        tools=_read_workspace_file(workspace, BOT_FILE_KEYS["tools"]),
        agents=_read_workspace_file(workspace, BOT_FILE_KEYS["agents"]),
    )


@router.put("/{key}", response_model=BotFileUpdateResponse)
async def update_bot_file(
    key: str,
    request: BotFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> BotFileUpdateResponse:
    """Update a bot profile MD file (SOUL, USER, HEARTBEAT, TOOLS, AGENTS)."""
    if key not in BOT_FILE_KEYS:
        raise HTTPException(
            status_code=400, detail=f"Invalid key. Must be one of: {list(BOT_FILE_KEYS.keys())}"
        )
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    filename = BOT_FILE_KEYS[key]
    path = workspace / filename
    path.write_text(request.content, encoding="utf-8")
    return BotFileUpdateResponse(key=key)

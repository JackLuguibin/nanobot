"""API routes for memory, workspace and bot-files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.workspace import BotFileUpdateRequest, WorkspaceFileUpdateRequest

router = APIRouter(prefix="/workspace")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@router.get("/memory")
async def get_memory(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Get long-term memory (MEMORY.md) and history (HISTORY.md)."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    from nanobot.agent.memory import MemoryStore

    store = MemoryStore(workspace)
    return {
        "long_term": store.read_long_term(),
        "history": store.history_file.read_text(encoding="utf-8")
        if store.history_file.exists()
        else "",
    }


# ---------------------------------------------------------------------------
# Workspace Files
# ---------------------------------------------------------------------------


def _read_workspace_file(workspace: Path, filename: str) -> str:
    """Read a file from workspace, return empty string if not found."""
    path = workspace / filename
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _resolve_workspace_path(workspace: Path, rel_path: str) -> Path | None:
    """Resolve relative path within workspace. Returns None if path escapes workspace."""
    if not workspace or not workspace.exists():
        return None
    try:
        resolved = (workspace / rel_path).resolve()
        if not str(resolved).startswith(str(workspace.resolve())):
            return None
        return resolved
    except (OSError, ValueError):
        return None


@router.get("/files")
async def list_workspace_files(
    path: str = Query("", description="Relative path from workspace root"),
    depth: int = Query(2, ge=1, le=5),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """List workspace directory structure. depth limits recursion."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path or ".")
    if resolved is None or not resolved.exists():
        raise HTTPException(status_code=400, detail="Invalid path")

    def _list_dir(p: Path, d: int) -> list[dict]:
        if d <= 0:
            return []
        items = []
        for child in sorted(p.iterdir()):
            name = child.name
            if name.startswith(".") and name != ".env":
                continue
            rel = child.relative_to(workspace)
            item = {
                "name": name,
                "path": str(rel).replace("\\", "/"),
                "is_dir": child.is_dir(),
            }
            if child.is_dir() and d > 1:
                item["children"] = _list_dir(child, d - 1)
            items.append(item)
        return items

    return {"path": path or ".", "items": _list_dir(resolved, depth)}


@router.get("/file")
async def get_workspace_file(
    path: str = Query(..., description="Relative path from workspace root"),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Read a file from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"path": path, "content": content}


@router.put("/file")
async def update_workspace_file(
    request: WorkspaceFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Update a file in workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, request.path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        resolved.write_text(request.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "updated", "path": request.path}


# ---------------------------------------------------------------------------
# Bot Files
# ---------------------------------------------------------------------------

BOT_FILE_KEYS = {
    "soul": "SOUL.md",
    "user": "USER.md",
    "heartbeat": "HEARTBEAT.md",
    "tools": "TOOLS.md",
    "agents": "AGENTS.md",
}


@router.get("/bot-files")
async def get_bot_files(bot_id: str | None = Query(None)) -> dict[str, str]:
    """Get SOUL, USER, HEARTBEAT, TOOLS, AGENTS from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {key: _read_workspace_file(workspace, filename) for key, filename in BOT_FILE_KEYS.items()}


@router.put("/bot-files/{key}")
async def update_bot_file(
    key: str,
    request: BotFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
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
    return {"status": "updated", "key": key}

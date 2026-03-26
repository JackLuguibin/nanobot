"""API routes for memory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state

router = APIRouter(prefix="/memory")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("")
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

"""API routes for configuration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.api.websocket import get_connection_manager
from console.server.models.config import ConfigUpdateRequest

router = APIRouter(prefix="/config")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@router.get("")
async def get_config(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get the full configuration."""
    state = _resolve_state(bot_id)
    return await state.get_config()


@router.put("")
async def update_config(
    request: ConfigUpdateRequest, bot_id: str | None = Query(None)
) -> dict[str, Any]:
    """Update configuration."""
    state = _resolve_state(bot_id)
    result = await state.update_config(request.section.value, request.data)

    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception as e:
        logger.warning("Failed to broadcast status update: {}", e)

    return result


@router.get("/schema")
async def get_config_schema(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get the configuration schema."""
    state = _resolve_state(bot_id)
    return await state.get_config_schema()


@router.post("/validate")
async def validate_config(data: dict[str, Any], bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Validate configuration data."""
    state = _resolve_state(bot_id)
    return await state.validate_config(data)

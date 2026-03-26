"""API routes for configuration and environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.api.websocket import get_connection_manager
from console.server.models.config import ConfigUpdateRequest, EnvUpdateRequest

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


# ---------------------------------------------------------------------------
# Environment Variables
# ---------------------------------------------------------------------------


def _get_env_path(state) -> Path:
    """Get .env path for a bot state. Raises HTTPException if not available."""
    if state.bot_id == "_empty" or state.config_path is None:
        raise HTTPException(status_code=400, detail="No bot config path available")
    return state.config_path.parent / ".env"


@router.get("/env")
async def get_env(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get environment variables from the bot's .env file."""
    from dotenv import dotenv_values

    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    if not env_path.exists():
        return {"vars": {}}
    try:
        vars_dict = dotenv_values(env_path)
        return {"vars": {k: (v or "") for k, v in vars_dict.items()}}
    except Exception as e:
        logger.warning("Failed to read .env: {}", e)
        return {"vars": {}}


@router.put("/env")
async def update_env(request: EnvUpdateRequest, bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Update environment variables in the bot's .env file."""
    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for key, value in request.vars.items():
        if not key or "=" in key or "\n" in key:
            continue
        if not isinstance(value, str):
            value = str(value)
        if " " in value or "\n" in value or '"' in value or "=" in value or "#" in value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")

    try:
        env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write .env: {}", e)
        raise HTTPException(status_code=500, detail=f"Failed to save .env: {e}")

    return {"status": "ok", "vars": request.vars}

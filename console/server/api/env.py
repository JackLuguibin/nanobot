"""API routes for environment variables — /api/v1/env."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state
from console.server.models.env import EnvVarsResponse, EnvUpdateRequest, EnvUpdateResponse

router = APIRouter(prefix="/env")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


def _get_env_path(state) -> str | None:
    """Get .env path for a bot state. Returns None for non-persistent bots."""
    if state.bot_id == "_empty" or state.config_path is None:
        return None
    return str(state.config_path.parent / ".env")


@router.get("", response_model=EnvVarsResponse)
async def get_env(bot_id: str | None = Query(None)) -> EnvVarsResponse:
    """Get environment variables from the bot's .env file."""
    from dotenv import dotenv_values

    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    if not env_path:
        return EnvVarsResponse(vars={})
    path = Path(env_path)
    if not path.exists():
        return EnvVarsResponse(vars={})
    try:
        vars_dict = dotenv_values(path)
        return EnvVarsResponse(vars={k: (v or "") for k, v in vars_dict.items()})
    except Exception as e:
        logger.warning("Failed to read .env: {}", e)
        return EnvVarsResponse(vars={})


@router.put("", response_model=EnvUpdateResponse)
async def update_env(request: EnvUpdateRequest, bot_id: str | None = Query(None)) -> EnvUpdateResponse:
    """Update environment variables in the bot's .env file."""
    state = _resolve_state(bot_id)
    env_path = _get_env_path(state)
    if not env_path:
        raise HTTPException(status_code=400, detail="No bot config path available")

    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)

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
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write .env: {}", e)
        raise HTTPException(status_code=500, detail=f"Failed to save .env: {e}")

    return EnvUpdateResponse(status="ok", vars=request.vars)
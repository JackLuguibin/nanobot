"""API routes for MCP server management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from console.server.api.state import get_state
from console.server.models.base import MCPStatus

router = APIRouter(prefix="/mcp")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[MCPStatus])
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


@router.post("/{name}/test")
async def test_mcp_connection(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Test connection to an MCP server by name."""
    state = _resolve_state(bot_id)
    return await state.test_mcp(name)


@router.post("/{name}/refresh")
async def refresh_mcp_server(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Reconnect an MCP server by name."""
    state = _resolve_state(bot_id)
    return await state.refresh_mcp(name)

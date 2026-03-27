"""API routes for MCP server management."""

from __future__ import annotations

from fastapi import APIRouter, Query

from console.server.api.state import get_state
from console.server.models.status import MCPStatus
from console.server.models.mcp import MCPRefreshResponse, MCPTestResponse

router = APIRouter(prefix="/mcp")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[MCPStatus])
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[MCPStatus]:
    """Get MCP server statuses."""
    state = _resolve_state(bot_id)
    status = await state.get_status()
    return [MCPStatus(**mcp) for mcp in status.get("mcp_servers", [])]


@router.post("/{name}/test", response_model=MCPTestResponse)
async def test_mcp_connection(
    name: str,
    bot_id: str | None = Query(None),
) -> MCPTestResponse:
    """Test connection to an MCP server by name."""
    state = _resolve_state(bot_id)
    raw = await state.test_mcp(name)
    return MCPTestResponse(**raw)


@router.post("/{name}/refresh", response_model=MCPRefreshResponse)
async def refresh_mcp_server(
    name: str,
    bot_id: str | None = Query(None),
) -> MCPRefreshResponse:
    """Reconnect an MCP server by name."""
    state = _resolve_state(bot_id)
    raw = await state.refresh_mcp(name)
    return MCPRefreshResponse(**raw)

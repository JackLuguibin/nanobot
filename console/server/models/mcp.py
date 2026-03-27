"""MCP server management models."""

from __future__ import annotations

from pydantic import BaseModel


class MCPTestResponse(BaseModel):
    """Response body for POST /mcp/{name}/test."""

    name: str
    success: bool
    latency_ms: int | None = None
    message: str | None = None


class MCPRefreshResponse(BaseModel):
    """Response body for POST /mcp/{name}/refresh."""

    name: str
    success: bool
    message: str | None = None

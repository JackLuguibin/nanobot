"""Memory (long-term / history) models."""

from __future__ import annotations

from pydantic import BaseModel


class MemoryResponse(BaseModel):
    """Response body for GET /memory."""

    long_term: str
    history: str

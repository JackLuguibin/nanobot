"""Bot management models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BotCreateRequest(BaseModel):
    name: str
    source_config: dict[str, Any] | None = None


class BotInfoResponse(BaseModel):
    id: str
    name: str
    config_path: str
    workspace_path: str
    created_at: str
    updated_at: str
    is_default: bool = False
    running: bool = False


class SetDefaultRequest(BaseModel):
    bot_id: str

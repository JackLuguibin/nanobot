"""Message queue monitoring models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChannelQueueStatus(BaseModel):
    inbound_size: int = 0
    outbound_size: int = 0


class ZMQQueueStatus(BaseModel):
    is_initialized: bool = False
    inbound_size: int = 0
    outbound_size: int = 0
    error: str | None = None


class QueueStatusResponse(BaseModel):
    """Queue status for a single bot."""

    bot_id: str
    channel_queue: ChannelQueueStatus
    zmq_queue: ZMQQueueStatus
    last_updated: datetime


class AllQueueStatusResponse(BaseModel):
    """Aggregated queue status across all bots."""

    statuses: list[QueueStatusResponse]

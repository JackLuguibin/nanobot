"""Scheduled / cron job models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class CronScheduleKind(str, Enum):
    AT = "at"
    EVERY = "every"
    CRON = "cron"


class CronScheduleInput(BaseModel):
    kind: CronScheduleKind
    at_ms: int | None = None
    every_ms: int | None = None
    expr: str | None = None
    tz: str | None = None


class CronAddRequest(BaseModel):
    name: str
    schedule: CronScheduleInput
    message: str = ""
    deliver: bool = False
    channel: str | None = None
    to: str | None = None
    delete_after_run: bool = False


class CronJobResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    schedule: dict[str, Any]
    payload: dict[str, Any]
    state: dict[str, Any]
    created_at_ms: int
    updated_at_ms: int
    delete_after_run: bool

"""Plans (kanban board) models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PlansSaveRequest(BaseModel):
    """Request body for saving plans board."""

    id: str
    name: str | None = None
    columns: list[dict[str, Any]]
    tasks: list[dict[str, Any]]


class PlanTaskCreateRequest(BaseModel):
    """Request body for creating a task."""

    title: str
    description: str | None = None
    columnId: str = "col-backlog"
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    progress: int | None = None
    project: str | None = None


class PlanTaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    title: str | None = None
    description: str | None = None
    columnId: str | None = None
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    progress: int | None = None
    project: str | None = None


class PlanColumn(BaseModel):
    id: str
    title: str
    order: int


class PlansBoardResponse(BaseModel):
    """Plans board response (GET /plans)."""

    id: str
    name: str
    columns: list[PlanColumn]
    tasks: list[dict[str, Any]]


class PlanTaskResponse(BaseModel):
    """Single task response (POST/PUT /plans/tasks)."""

    id: str
    title: str
    description: str | None = None
    columnId: str
    order: int
    createdAt: str
    updatedAt: str
    priority: str | None = None
    startDate: str | None = None
    dueDate: str | None = None
    progress: int | None = None
    project: str | None = None


class PlanTaskDeleteResponse(BaseModel):
    """Response for DELETE /plans/tasks/{task_id}."""

    status: str = "deleted"
    task_id: str

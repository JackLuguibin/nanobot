"""API routes for Plans (kanban board)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.plans import PlanTaskCreateRequest, PlanTaskUpdateRequest, PlansSaveRequest

router = APIRouter(prefix="/plans")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def get_plans(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """Get Plans kanban board data."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        return {
            "id": "board-default",
            "name": "默认看板",
            "columns": [
                {"id": "col-backlog", "title": "待办", "order": 0},
                {"id": "col-progress", "title": "进行中", "order": 1},
                {"id": "col-done", "title": "已完成", "order": 2},
            ],
            "tasks": [],
        }
    from console.server.extension.plans import get_plans as _get_plans

    return _get_plans(state.bot_id)


@router.put("")
async def save_plans(
    request: PlansSaveRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Save Plans kanban board data."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")
    from console.server.extension.plans import save_plans as _save_plans

    data = {
        "id": request.id,
        "name": request.name,
        "columns": request.columns,
        "tasks": request.tasks,
    }
    _save_plans(state.bot_id, data)
    return data


@router.post("/tasks")
async def create_plan_task(
    request: PlanTaskCreateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Create a new task in Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans

    board = _get_plans(state.bot_id)
    now = time.time()

    task_id = f"task-{int(now * 1000)}"

    new_task = {
        "id": task_id,
        "title": request.title,
        "description": request.description,
        "columnId": request.columnId,
        "order": len([t for t in board.get("tasks", []) if t.get("columnId") == request.columnId]),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if request.priority:
        new_task["priority"] = request.priority
    if request.startDate:
        new_task["startDate"] = request.startDate
    if request.dueDate:
        new_task["dueDate"] = request.dueDate
    if request.progress is not None:
        new_task["progress"] = request.progress
    if request.project:
        new_task["project"] = request.project

    tasks = board.get("tasks", [])
    tasks.append(new_task)
    board["tasks"] = tasks
    _save_plans(state.bot_id, board)

    return new_task


@router.put("/tasks/{task_id}")
async def update_plan_task(
    task_id: str,
    request: PlanTaskUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Update an existing task in Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans

    board = _get_plans(state.bot_id)
    tasks = board.get("tasks", [])

    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if request.title is not None:
        task["title"] = request.title
    if request.description is not None:
        task["description"] = request.description
    if request.columnId is not None:
        task["columnId"] = request.columnId
    if request.priority is not None:
        task["priority"] = request.priority
    if request.startDate is not None:
        task["startDate"] = request.startDate
    if request.dueDate is not None:
        task["dueDate"] = request.dueDate
    if request.progress is not None:
        task["progress"] = request.progress
    if request.project is not None:
        task["project"] = request.project

    task["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    board["tasks"] = tasks
    _save_plans(state.bot_id, board)

    return task


@router.delete("/tasks/{task_id}")
async def delete_plan_task(
    task_id: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Delete a task from Plans."""
    state = _resolve_state(bot_id)
    if state.bot_id == "_empty":
        raise HTTPException(status_code=400, detail="No bot selected")

    from console.server.extension.plans import get_plans as _get_plans, save_plans as _save_plans

    board = _get_plans(state.bot_id)
    tasks = board.get("tasks", [])

    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    board["tasks"] = [t for t in tasks if t.get("id") != task_id]
    _save_plans(state.bot_id, board)

    return {"status": "deleted", "task_id": task_id}

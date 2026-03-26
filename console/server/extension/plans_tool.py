"""Plans Tool - 任务计划管理的 CLI 工具。

提供命令行接口来操作 Plans 看板数据。
"""

from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool


class PlansTool(Tool):
    """Plans CLI 工具，用于管理任务计划。"""

    def __init__(self, base_url: str = "http://localhost:18791"):
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return """管理任务计划看板。可以创建、查看、更新、删除任务。

支持的操作：
- list: 查看所有任务
- create: 创建新任务
- update: 更新任务
- delete: 删除任务
- move: 移动任务到不同状态列"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "update", "delete", "move"],
                    "description": "操作类型：list(查看), create(创建), update(更新), delete(删除), move(移动)",
                },
                "title": {
                    "type": "string",
                    "description": "任务标题（create/update 时必填）",
                },
                "task_id": {
                    "type": "string",
                    "description": "任务ID（update/delete/move 时必填）",
                },
                "description": {
                    "type": "string",
                    "description": "任务描述（可选），详细说明任务内容",
                },
                "project": {
                    "type": "string",
                    "description": "所属项目（可选），用于在看板中按项目分组任务",
                },
                "column": {
                    "type": "string",
                    "enum": ["backlog", "progress", "done"],
                    "description": "状态列：backlog(待办), progress(进行中), done(已完成)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "优先级：high(高), medium(中), low(低)",
                },
                "start_date": {
                    "type": "string",
                    "description": "开始时间（可选），ISO 8601 格式，如 2024-01-10T09:00:00，用于甘特图显示",
                },
                "due_date": {
                    "type": "string",
                    "description": "截止时间，ISO 8601 格式，如 2024-01-15T18:00:00",
                },
                "progress": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "进度，0-100",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """执行 Plans 操作。"""
        action = kwargs.get("action", "list")

        try:
            if action == "list":
                return await self._list_tasks()
            elif action == "create":
                return await self._create_task(kwargs)
            elif action == "update":
                return await self._update_task(kwargs)
            elif action == "delete":
                return await self._delete_task(kwargs)
            elif action == "move":
                return await self._move_task(kwargs)
            else:
                return f"Error: Unknown action '{action}'"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _list_tasks(self) -> str:
        """列出所有任务。"""
        import httpx

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self._base_url}/api/v1/plans", timeout=10.0)
            except Exception as e:
                return f"Error: 无法连接到服务器 - {str(e)}"

            if resp.status_code == 200:
                data = resp.json()
                tasks = data.get("tasks", [])
                if not tasks:
                    return "当前没有任务。"

                columns = {c["id"]: c["title"] for c in data.get("columns", [])}
                result = ["# 任务列表\n"]
                for task in tasks:
                    col_name = columns.get(task.get("columnId"), "未知")
                    priority = task.get("priority", "")
                    progress = task.get("progress")
                    due = task.get("dueDate", "")
                    start = task.get("startDate", "")
                    project = task.get("project", "")

                    line = f"- [{task['id'][:12]}...] {task['title']}"
                    if project:
                        line += f" [项目:{project}]"
                    if priority:
                        line += f" [优先级:{priority}]"
                    if col_name:
                        line += f" [{col_name}]"
                    if progress is not None:
                        line += f" ({progress}%)"
                    if start or due:
                        line += " 时间:"
                        if start:
                            line += f"{start[:10]}"
                        if start and due:
                            line += " ~ "
                        if due:
                            line += f"{due[:10]}"
                    result.append(line)

                return "\n".join(result)
            else:
                return f"Error: Failed to fetch plans (status {resp.status_code})"

    async def _create_task(self, params: dict[str, Any]) -> str:
        """创建任务。"""
        import httpx

        title = params.get("title")
        if not title:
            return "Error: title is required for create action"

        # Map column names to IDs
        column_map = {"backlog": "col-backlog", "progress": "col-progress", "done": "col-done"}
        column_id = column_map.get(params.get("column", "backlog"), "col-backlog")

        payload = {
            "title": title,
            "description": params.get("description"),
            "columnId": column_id,
            "priority": params.get("priority"),
            "startDate": params.get("start_date"),
            "dueDate": params.get("due_date"),
            "progress": params.get("progress"),
            "project": params.get("project"),
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"{self._base_url}/api/v1/plans/tasks", json=payload, timeout=10.0)
            except Exception as e:
                return f"Error: 无法连接到服务器 - {str(e)}"

            if resp.status_code == 200:
                task = resp.json()
                task_info = f"任务创建成功: {task['title']} (ID: {task['id'][:12]}...)"
                if task.get("project"):
                    task_info += f"\n项目: {task['project']}"
                if task.get("startDate"):
                    task_info += f"\n开始时间: {task['startDate']}"
                if task.get("dueDate"):
                    task_info += f"\n截止时间: {task['dueDate']}"
                return task_info
            else:
                return f"Error: Failed to create task (status {resp.status_code}): {resp.text}"

    async def _update_task(self, params: dict[str, Any]) -> str:
        """更新任务。"""
        import httpx

        task_id = params.get("task_id")
        if not task_id:
            return "Error: task_id is required for update action"

        column_map = {"backlog": "col-backlog", "progress": "col-progress", "done": "col-done"}

        payload = {}
        if params.get("title"):
            payload["title"] = params["title"]
        if params.get("description") is not None:
            payload["description"] = params["description"]
        if params.get("column"):
            payload["columnId"] = column_map.get(params["column"], params["column"])
        if params.get("priority"):
            payload["priority"] = params["priority"]
        if params.get("start_date") is not None:
            payload["startDate"] = params["start_date"]
        if params.get("due_date") is not None:
            payload["dueDate"] = params["due_date"]
        if params.get("progress") is not None:
            payload["progress"] = params["progress"]
        if params.get("project") is not None:
            payload["project"] = params["project"]

        if not payload:
            return "Error: No fields to update"

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.put(f"{self._base_url}/api/v1/plans/tasks/{task_id}", json=payload, timeout=10.0)
            except Exception as e:
                return f"Error: 无法连接到服务器 - {str(e)}"

            if resp.status_code == 200:
                task = resp.json()
                return f"✓ 任务更新成功: {task['title']}"
            else:
                return f"Error: Failed to update task (status {resp.status_code}): {resp.text}"

    async def _delete_task(self, params: dict[str, Any]) -> str:
        """删除任务。"""
        import httpx

        task_id = params.get("task_id")
        if not task_id:
            return "Error: task_id is required for delete action"

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.delete(f"{self._base_url}/api/v1/plans/tasks/{task_id}", timeout=10.0)
            except Exception as e:
                return f"Error: 无法连接到服务器 - {str(e)}"

            if resp.status_code == 200:
                return f"✓ 任务已删除 (ID: {task_id[:12]}...)"
            else:
                return f"Error: Failed to delete task (status {resp.status_code}): {resp.text}"

    async def _move_task(self, params: dict[str, Any]) -> str:
        """移动任务到不同状态列。"""
        column_map = {"backlog": "col-backlog", "progress": "col-progress", "done": "col-done"}

        column = params.get("column", "backlog")
        params["columnId"] = column_map.get(column, column)

        return await self._update_task(params)


# CLI 入口函数（用于直接命令行调用）
async def run_plans_cli(args: list[str] | None = None) -> str:
    """CLI 入口，供命令行直接调用。"""
    import argparse

    parser = argparse.ArgumentParser(description="Plans 任务管理 CLI")
    parser.add_argument("action", choices=["list", "create", "update", "delete", "move"], help="操作类型")
    parser.add_argument("--title", help="任务标题")
    parser.add_argument("--task-id", help="任务ID")
    parser.add_argument("--description", help="任务描述")
    parser.add_argument("--project", help="所属项目")
    parser.add_argument("--column", choices=["backlog", "progress", "done"], help="状态列")
    parser.add_argument("--priority", choices=["high", "medium", "low"], help="优先级")
    parser.add_argument("--start-date", help="开始时间")
    parser.add_argument("--due-date", help="截止时间")
    parser.add_argument("--progress", type=int, help="进度 0-100")

    parsed = parser.parse_args(args or [])

    tool = PlansTool()
    return await tool.execute(**vars(parsed))

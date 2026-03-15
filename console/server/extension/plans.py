"""Plans 看板持久化扩展。

将 Plans 看板数据存储到 bot 目录下的 plans.json。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _get_plans_path(bot_id: str) -> Path:
    """获取 plans 文件路径。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "plans.json"
    except Exception:
        pass
    return Path.home() / ".nanobot" / "bots" / bot_id / "plans.json"


def get_plans(bot_id: str) -> dict[str, Any]:
    """加载 Plans 看板数据。"""
    path = _get_plans_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
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
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("columns"):
            data["columns"] = [
                {"id": "col-backlog", "title": "待办", "order": 0},
                {"id": "col-progress", "title": "进行中", "order": 1},
                {"id": "col-done", "title": "已完成", "order": 2},
            ]
        if "tasks" not in data:
            data["tasks"] = []
        return data
    except Exception:
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


def save_plans(bot_id: str, data: dict[str, Any]) -> None:
    """保存 Plans 看板数据。"""
    path = _get_plans_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

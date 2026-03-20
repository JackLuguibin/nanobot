"""Plans Skill - 任务计划管理。

本 skill 提供任务计划管理能力，包括创建、查询、更新和删除任务。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


def get_plans_skill_content() -> str:
    """获取 Plans skill 的完整内容。"""
    return """# Plans 任务计划管理

你可以使用 Plans skill 来管理任务计划。这是一个看板+甘特图式的任务管理系统。

## 使用 plan 工具

通过 `plan` 工具可以管理任务。

### 查看任务列表
```
plan action=list
```

### 创建新任务
```
plan action=create title="任务标题" description="任务描述" project="项目名称" priority=high start_date="2024-01-10T09:00:00" due_date="2024-01-15T18:00:00" progress=0 column=backlog
```

参数说明：
- action: 操作类型，必填
- title: 任务标题，create 时必填
- description: 任务描述（可选），详细说明任务内容
- project: 所属项目（可选），用于在看板中按项目分组任务
- column: 状态列，可选值: backlog(待办), progress(进行中), done(已完成)
- priority: 优先级，可选值: high(高), medium(中), low(低)
- start_date: 开始时间（可选），ISO 8601 格式，如 2024-01-10T09:00:00，用于甘特图显示
- due_date: 截止时间（可选），ISO 8601 格式，如 2024-01-15T18:00:00，用于甘特图显示
- progress: 进度，0-100 的数字

### 更新任务
```
plan action=update task_id=xxx title="新标题" priority=low progress=50
```

### 删除任务
```
plan action=delete task_id=xxx
```

### 移动任务到不同状态
```
plan action=move task_id=xxx column=done
```

## 状态列说明

- **backlog**: 待办 - 新创建的任务默认在此列
- **progress**: 进行中 - 正在处理的任务
- **done**: 已完成 - 已完成的任务

## 使用示例

用户说 "帮我创建一个任务：完成项目报告，属于'年度报告'项目，截止到1月15日"
-> 使用 plan 工具，action=create, title="完成项目报告", project="年度报告", due_date="2024-01-15T18:00:00"

用户说 "创建一个开发任务，前端页面开发，属于'网站重构'项目，从1月10日开始，1月20日结束，优先级高"
-> 使用 plan 工具，action=create, title="前端页面开发", project="网站重构", start_date="2024-01-10T09:00:00", due_date="2024-01-20T18:00:00", priority="high"

用户说 "查看所有待办任务"
-> 使用 plan 工具，action=list

用户说 "把任务 xxx 标记为已完成"
-> 使用 plan 工具，action=move, task_id=xxx, column=done

用户说 "删除任务 xxx"
-> 使用 plan 工具，action=delete, task_id=xxx

用户说 "更新任务 xxx 的进度为 50%"
-> 使用 plan 工具, action=update, task_id=xxx, progress=50

## 注意事项

1. 所有时间格式使用 ISO 8601 格式（如 2024-01-15T18:00:00）
2. 任务创建后会在前端页面（Plans）中显示
3. project 参数用于任务分组，在看板视图中可以按项目筛选
4. start_date 和 due_date 用于在甘特图中展示任务时间线
5. 使用 column 参数移动任务到不同状态
6. 创建任务时，建议同时提供 start_date 和 due_date，以便在甘特图中正确显示任务周期
"""


def ensure_plans_skill(workspace: Path) -> bool:
    """确保 Plans skill 存在于 workspace 中。

    如果不存在则创建。
    """
    if not workspace or not workspace.exists():
        return False

    skill_dir = workspace / "skills" / "plans"
    if skill_dir.exists():
        return True  # 已存在

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = get_plans_skill_content()
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        logger.debug("Failed to ensure plans skill: {}", e)
        return False


def patch_plans_skill(workspace: Path) -> None:
    """Patch 函数：在 workspace 中创建 Plans skill。

    供 main.py 调用。
    """
    try:
        ensure_plans_skill(workspace)
    except Exception as e:
        logger.debug("Failed to patch plans skill: {}", e)
        pass  # 静默失败，不影响 agent 正常运行

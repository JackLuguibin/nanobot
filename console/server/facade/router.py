"""
facade/router.py - Facade REST API 路由

所有 API 端点统一路由，全部基于 Facade 层。
设计原则：
- 所有端点通过 Facade 层调用
- 使用 Facade 层 OperationResult 返回格式
- 统一错误处理
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Path as PathParam, Body, HTTPException
from typing import Any

from console.server.facade.state.manager import StateFacade
from console.server.facade.init import get_facade_manager

router = APIRouter(tags=["facade"])


def _get_facade(bot_id: str | None = None) -> StateFacade | None:
    """从全局 FacadeManager 获取 StateFacade。"""
    manager = get_facade_manager()
    return manager.get_facade_or_default(bot_id)


def _bot_facade():
    """获取系统级 BotFacade。"""
    return get_facade_manager().get_bot_facade()


def _ok(result):
    """统一成功响应。"""
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return result


def _require(facade, name="facade"):
    if not facade:
        raise HTTPException(status_code=503, detail=f"No {name} available")
    return facade


# -------------------------------------------------------------------------
# Bot Management（系统级，非 per-bot）
# -------------------------------------------------------------------------

@router.get("/bots")
async def list_bots() -> list[dict[str, Any]]:
    """列出所有 Bot（BotFacade）。"""
    bf = _bot_facade()
    return bf.list()


@router.get("/bots/{bot_id}")
async def get_bot(bot_id: str) -> dict[str, Any]:
    """获取指定 Bot 详情。"""
    bf = _bot_facade()
    result = bf.get(bot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return result


@router.post("/bots")
async def create_bot(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """创建新 Bot。"""
    bf = _bot_facade()
    result = await bf.create(data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.put("/bots/{bot_id}")
async def update_bot(bot_id: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """更新 Bot 信息。"""
    bf = _bot_facade()
    result = await bf.update(bot_id, data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str) -> dict[str, Any]:
    """删除 Bot。"""
    bf = _bot_facade()
    result = await bf.delete(bot_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str) -> dict[str, Any]:
    """启动 Bot。"""
    bf = _bot_facade()
    result = await bf.start(bot_id)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.to_dict()


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str) -> dict[str, Any]:
    """停止 Bot。"""
    bf = _bot_facade()
    result = await bf.stop(bot_id)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.to_dict()


@router.put("/bots/default")
async def set_default_bot(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """设置默认 Bot。"""
    bf = _bot_facade()
    result = await bf.set_default(data.get("bot_id", ""))
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


# -------------------------------------------------------------------------
# Unified Status
# -------------------------------------------------------------------------

@router.get("/status")
async def get_status(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取统一状态（Facade 层）。"""
    facade = _get_facade(bot_id)
    if not facade or not facade._status_facade:
        raise HTTPException(status_code=503, detail="No facade available")
    return await facade._status_facade.get_status()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """健康检查。"""
    from datetime import datetime
    from nanobot import __version__
    return {"status": "healthy", "version": __version__, "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/audit")
async def health_audit(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """健康审计。"""
    facade = _get_facade(bot_id)
    if not facade or not facade._status_facade:
        raise HTTPException(status_code=503, detail="No facade available")
    from console.server.extension.health import run_health_audit
    from nanobot.config.schema import Config
    state = facade._status_facade
    config = await state.get_status()
    issues = run_health_audit(facade.bot_id, state._workspace, config, config)
    return {"issues": issues}


@router.get("/gateway/status")
async def get_gateway_status(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取 Gateway 状态。"""
    facade = _get_facade(bot_id)
    _require(facade, "facade")
    return facade.get_gateway_status()


# -------------------------------------------------------------------------
# Channel
# -------------------------------------------------------------------------

@router.get("/channels")
async def list_channels(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """列出所有通道。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "channel facade")
    return facade._channel_facade.list()


@router.patch("/channels/{name}")
async def update_channel(
    name: str = PathParam(...),
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新通道配置。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "channel facade")
    result = await facade._channel_facade.update(name, data)
    return result.to_dict()


@router.delete("/channels/{name}")
async def delete_channel(
    name: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """禁用通道。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "channel facade")
    result = await facade._channel_facade.delete(name)
    return result.to_dict()


@router.post("/channels/{name}/refresh")
async def refresh_channel(
    name: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """刷新通道（运行时重启）。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "channel facade")
    result = await facade._channel_facade.stop(name)
    return result.to_dict()


@router.post("/channels/refresh")
async def refresh_all_channels(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """刷新所有通道。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "channel facade")
    channels = facade._channel_facade.list()
    results = []
    for ch in channels:
        if ch.get("status") == "online":
            r = await facade._channel_facade.stop(ch["name"])
            results.append(r.to_dict())
    return {"results": results}


# -------------------------------------------------------------------------
# Session
# -------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """列出会话。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._session_facade, "session facade")
    return facade._session_facade.list()


@router.get("/sessions/{key}")
async def get_session(
    key: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any] | None:
    """获取会话详情。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._session_facade, "session facade")
    return facade._session_facade.get(key)


@router.post("/sessions")
async def create_session(
    key: str | None = Query(None),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """创建会话。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._session_facade, "session facade")
    result = await facade._session_facade.create({"key": key} if key else {})
    return result.to_dict()


@router.delete("/sessions/{key}")
async def delete_session(
    key: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """删除会话。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._session_facade, "session facade")
    result = await facade._session_facade.delete(key)
    return result.to_dict()


# -------------------------------------------------------------------------
# Config
# -------------------------------------------------------------------------

@router.get("/config")
async def get_config(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取完整配置。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "facade")
    # 从 ConfigBridge 获取原始配置
    if hasattr(facade._channel_facade, "_config_bridge") and facade._channel_facade._config_bridge:
        return facade._channel_facade._config_bridge.load_raw()
    return {}


@router.put("/config")
async def update_config(
    section: str = Query(...),
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新配置节。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._channel_facade, "facade")
    bridge = facade._channel_facade._config_bridge
    if not bridge:
        raise HTTPException(status_code=503, detail="ConfigBridge not available")
    current = bridge.load_raw()
    if section not in current:
        current[section] = {}
    current[section].update(data)
    bridge.save(current)
    return current


@router.get("/config/schema")
async def get_config_schema(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取配置 Schema。"""
    from nanobot.config.schema import Config
    return Config.model_json_schema()


@router.post("/config/validate")
async def validate_config(
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """验证配置。"""
    try:
        from nanobot.config.schema import Config
        Config(**data)
        return {"valid": True, "errors": []}
    except Exception as e:
        return {"valid": False, "errors": [str(e)]}


# -------------------------------------------------------------------------
# Cron
# -------------------------------------------------------------------------

@router.get("/cron")
async def list_cron_jobs(
    bot_id: str | None = Query(None),
    include_disabled: bool = Query(False),
) -> list[dict[str, Any]]:
    """列出 Cron 任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    return facade._cron_facade.list()


@router.post("/cron")
async def create_cron_job(
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """创建 Cron 任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    result = await facade._cron_facade.create(data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.patch("/cron/{job_id}")
async def update_cron_job(
    job_id: str = PathParam(...),
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新 Cron 任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    result = await facade._cron_facade.update(job_id, data)
    return result.to_dict()


@router.delete("/cron/{job_id}")
async def delete_cron_job(
    job_id: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """删除 Cron 任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    result = await facade._cron_facade.delete(job_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.to_dict()


@router.post("/cron/{job_id}/run")
async def run_cron_job(
    job_id: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """手动触发 Cron 任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    result = await facade._cron_facade.run(job_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.to_dict()


@router.get("/cron/status")
async def get_cron_status(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取 Cron 服务状态。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._cron_facade, "cron facade")
    return facade._cron_facade.health_check().to_dict()


@router.get("/cron/history")
async def get_cron_history(
    bot_id: str | None = Query(None),
    job_id: str | None = Query(None),
) -> dict[str, list[dict[str, Any]]]:
    """获取 Cron 执行历史。"""
    facade = _get_facade(bot_id)
    _require(facade, "facade")
    from console.server.extension.cron_history import get_cron_history as _get
    return _get(facade.bot_id, job_id)


# -------------------------------------------------------------------------
# Environment Variables
# -------------------------------------------------------------------------

@router.get("/env")
async def get_env(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取环境变量。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._env_facade, "env facade")
    vars_list = facade._env_facade.list()
    return {"vars": {v["key"]: v["value"] for v in vars_list}}


@router.put("/env")
async def update_env(
    vars_dict: dict[str, str] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新环境变量。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._env_facade, "env facade")
    result = await facade._env_facade.update_batch(vars_dict)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {"status": "ok", "vars": vars_dict}


# -------------------------------------------------------------------------
# Bot Files
# -------------------------------------------------------------------------

@router.get("/bot-files")
async def get_bot_files(bot_id: str | None = Query(None)) -> dict[str, str]:
    """获取 Bot 配置文件（SOUL, USER, HEARTBEAT, TOOLS, AGENTS）。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._workspace_facade, "workspace facade")
    return await facade._workspace_facade.get_bot_files()


@router.put("/bot-files/{key}")
async def update_bot_file(
    key: str = PathParam(...),
    content: str = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新 Bot 配置文件。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._workspace_facade, "workspace facade")
    result = await facade._workspace_facade.update_bot_file(key, content)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


# -------------------------------------------------------------------------
# Workspace Files
# -------------------------------------------------------------------------

@router.get("/workspace/files")
async def list_workspace_files(
    path: str = Query(""),
    depth: int = Query(2, ge=1, le=5),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """列出工作区文件。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._workspace_facade, "workspace facade")
    wf = facade._workspace_facade
    if not wf._workspace or not wf._workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")
    resolved = wf._resolve_path(path or ".")
    if resolved is None or not resolved.exists():
        raise HTTPException(status_code=400, detail="Invalid path")
    items = wf._list_dir(resolved, depth)
    return {"path": path or ".", "items": items}


@router.get("/workspace/file")
async def get_workspace_file(
    path: str = Query(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """读取工作区文件。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._workspace_facade, "workspace facade")
    result = facade._workspace_facade.get(path)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result


@router.put("/workspace/file")
async def update_workspace_file(
    path: str = Query(...),
    content: str = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新工作区文件。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._workspace_facade, "workspace facade")
    result = await facade._workspace_facade.update(path, {"content": content})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return result.to_dict()


# -------------------------------------------------------------------------
# Plans
# -------------------------------------------------------------------------

@router.get("/plans")
async def get_plans(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """获取 Plans 看板。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._plans_facade, "plans facade")
    return facade._plans_facade._get_board()


@router.put("/plans")
async def save_plans(
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """保存 Plans 看板数据。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._plans_facade, "plans facade")
    result = await facade._plans_facade.create(data)
    return result.to_dict()


@router.post("/plans/tasks")
async def create_plan_task(
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """创建任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._plans_facade, "plans facade")
    result = await facade._plans_facade.create_task(data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.put("/plans/tasks/{task_id}")
async def update_plan_task(
    task_id: str = PathParam(...),
    data: dict[str, Any] = Body(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """更新任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._plans_facade, "plans facade")
    result = await facade._plans_facade.update_task(task_id, data)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.to_dict()


@router.delete("/plans/tasks/{task_id}")
async def delete_plan_task(
    task_id: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """删除任务。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._plans_facade, "plans facade")
    result = await facade._plans_facade.delete(task_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.to_dict()


# -------------------------------------------------------------------------
# Activity & Alerts
# -------------------------------------------------------------------------

@router.get("/activity")
async def get_activity(
    bot_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    activity_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """获取活动日志。"""
    facade = _get_facade(bot_id)
    if not facade:
        return []
    from console.server.extension.activity import get_activity as _get
    return _get(facade.bot_id, limit=limit, activity_type=activity_type)


@router.get("/alerts")
async def get_alerts(
    bot_id: str | None = Query(None),
    include_dismissed: bool = Query(False),
) -> list[dict[str, Any]]:
    """获取告警列表。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._alert_facade, "alert facade")
    return facade._alert_facade.list()


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """关闭告警。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._alert_facade, "alert facade")
    result = await facade._alert_facade.delete(alert_id)
    return result.to_dict()


# -------------------------------------------------------------------------
# Tools
# -------------------------------------------------------------------------

@router.get("/tools/log")
async def get_tool_logs(
    limit: int = Query(50, ge=1, le=200),
    tool_name: str | None = Query(None),
    bot_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """获取工具调用日志。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._tools_facade, "tools facade")
    return facade._tools_facade._collect_logs(limit=limit, tool_name=tool_name)


# -------------------------------------------------------------------------
# Usage
# -------------------------------------------------------------------------

@router.get("/usage/history")
async def get_usage_history(
    bot_id: str | None = Query(None),
    days: int = Query(14, ge=1, le=90),
) -> list[dict[str, Any]]:
    """获取使用量历史。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._usage_facade, "usage facade")
    return await facade._usage_facade.get_history(days=days)


@router.get("/usage/cost")
async def get_usage_cost(
    bot_id: str | None = Query(None),
    date_str: str | None = Query(None),
) -> dict[str, Any]:
    """获取使用成本。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._usage_facade, "usage facade")
    return await facade._usage_facade.get_cost(date_str=date_str)


# -------------------------------------------------------------------------
# MCP
# -------------------------------------------------------------------------

@router.get("/mcp")
async def get_mcp_servers(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """获取 MCP 服务器状态。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._mcp_facade, "mcp facade")
    return facade._mcp_facade.list()


@router.post("/mcp/{name}/test")
async def test_mcp_connection(
    name: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """测试 MCP 连接。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._mcp_facade, "mcp facade")
    return await facade._mcp_facade.test(name)


@router.post("/mcp/{name}/refresh")
async def refresh_mcp_server(
    name: str = PathParam(...),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """重新连接 MCP 服务器。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._mcp_facade, "mcp facade")
    return await facade._mcp_facade.refresh(name)


# -------------------------------------------------------------------------
# Memory
# -------------------------------------------------------------------------

@router.get("/memory")
async def get_memory(bot_id: str | None = Query(None)) -> dict[str, str]:
    """获取长期记忆。"""
    facade = _get_facade(bot_id)
    _require(facade and facade._memory_facade, "memory facade")
    result = facade._memory_facade.get("long_term")
    if result is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"long_term": result.get("content", ""), "history": ""}


# -------------------------------------------------------------------------
# Queue
# -------------------------------------------------------------------------

@router.get("/queue/status")
async def get_queue_status(
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """获取队列状态。"""
    from console.server.api.state import get_state, get_state_manager
    manager = get_state_manager()
    if bot_id:
        state = get_state(bot_id)
        return await state.get_queue_status()
    raws = await manager.get_all_queue_status()
    return {"statuses": raws}


# -------------------------------------------------------------------------
# Control
# -------------------------------------------------------------------------

@router.post("/control/stop")
async def stop_current_task(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """停止当前任务。"""
    from console.server.api.state import get_state
    from console.server.api.websocket import get_connection_manager
    state = get_state(bot_id)
    success = await state.stop_current_task()
    if not success:
        raise HTTPException(status_code=400, detail="No task running or unable to stop")
    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception:
        pass
    return {}


@router.post("/control/restart")
async def restart_bot(bot_id: str | None = Query(None)) -> dict[str, Any]:
    """重启 Bot。"""
    from console.server.api.state import get_state
    from console.server.api.websocket import get_connection_manager
    state = get_state(bot_id)
    success = await state.restart_bot()
    if not success:
        raise HTTPException(status_code=400, detail="Unable to restart")
    try:
        manager = get_connection_manager()
        status = await state.get_status()
        await manager.broadcast_status_update(status, state.bot_id)
    except Exception:
        pass
    return {}


# -------------------------------------------------------------------------
# Operations（通用操作接口）
# -------------------------------------------------------------------------

@router.post("/operations")
async def execute_operation(
    operation: str = Body(...),
    resource_type: str = Body(...),
    resource_id: str = Body(...),
    data: dict[str, Any] = Body({}),
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """通用操作接口。"""
    facade = _get_facade(bot_id)
    _require(facade, "facade")
    result = await facade.execute_operation(operation, resource_type, resource_id, data)
    return result.to_dict()

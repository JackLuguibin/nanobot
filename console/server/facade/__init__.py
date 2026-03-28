"""
facade - Nanobot 后端管理层（Management Facade）

层次架构：
- facade/base.py        - 基础接口（BaseManager, OperationResult, HealthCheckResult, FacadeEvent）
- facade/config/        - 配置管理（loader, validator, diff）
- facade/agent/         - Agent 管理
- facade/channel/       - Channel 管理
- facade/session/       - Session 管理
- facade/cron/          - Cron 管理
- facade/provider/     - Provider 管理
- facade/skill/         - Skill 管理
- facade/bot/           - Bot 生命周期管理
- facade/status/        - 统一状态收集
- facade/alert/         - 告警管理
- facade/usage/         - Token 使用量追踪
- facade/tools/         - 工具调用日志
- facade/workspace/     - 工作区文件管理
- facade/plans/         - Plans 看板管理
- facade/env/           - 环境变量管理
- facade/mcp/           - MCP 服务器管理
- facade/memory/        - 长期记忆管理
- facade/state/         - 统一状态管理（StateFacade）
- facade/api.py         - Facade API 适配层
- facade/router.py      - Facade REST API 路由
- facade/init.py        - Facade 层初始化
"""

from console.server.facade.base import (
    BaseManager,
    FacadeEvent,
    FacadeEventType,
    HealthCheckResult,
    HealthStatus,
    OperationResult,
    OperationStatus,
)
from console.server.facade.state.manager import StateFacade, UnifiedStatus
from console.server.facade.init import get_facade_manager, initialize_facade_layer, shutdown_facade_layer
from console.server.facade.api import FacadeAPI

__all__ = [
    "BaseManager",
    "FacadeEvent",
    "FacadeEventType",
    "HealthCheckResult",
    "HealthStatus",
    "OperationResult",
    "OperationStatus",
    "StateFacade",
    "UnifiedStatus",
    "FacadeAPI",
    "get_facade_manager",
    "initialize_facade_layer",
    "shutdown_facade_layer",
]
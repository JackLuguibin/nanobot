"""
facade/api.py - Facade API 适配层

Facade 层与现有 API 的适配。
现有 API 端点（api/state.py 等）保持不变，此模块提供 Facade 层入口。

设计原则：
- 现有 API 100% 兼容，前端无需改动
- 新端点通过 Facade 层调用
- Facade 层依赖现有 BotStateManager，但提供更清晰的接口
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class FacadeAPI:
    """
    Facade API 统一入口。

    此模块在现有 BotState API 基础上包装一层 Facade 接口，
    提供统一的操作入口，便于后续 API 层逐步迁移到 Facade 架构。

    设计原则：
    - 底层仍使用现有 BotStateManager（保持 100% 兼容）
    - 上层提供 Facade 风格的统一接口
    - 新增 /api/v1/status 统一状态端点（基于 Facade）
    """

    def __init__(self, state_manager: Any) -> None:
        self._state_manager = state_manager

    # -------------------------------------------------------------------------
    # 统一状态
    # -------------------------------------------------------------------------

    async def get_unified_status(self, bot_id: str | None = None) -> dict[str, Any]:
        """
        获取统一状态（并行收集所有组件健康状态）。
        底层使用 BotState.get_status() 收集数据。
        """
        state = self._state_manager.get_state(bot_id)
        status = await state.get_status()

        # 补充 Facade 层信息
        return {
            **status,
            "facade_version": "1.0",
            "bot_id": state.bot_id,
        }

    # -------------------------------------------------------------------------
    # Agent 操作（通过 Facade 风格封装）
    # -------------------------------------------------------------------------

    async def agent_health(self, bot_id: str | None = None) -> dict[str, Any]:
        """Agent 健康检查。"""
        state = self._state_manager.get_state(bot_id)
        agent_loop = state.agent_loop
        if not agent_loop:
            return {"status": "unhealthy", "message": "AgentLoop not initialized"}

        details = {
            "model": getattr(agent_loop, "model", None),
            "provider": (
                agent_loop._provider.__class__.__name__
                if hasattr(agent_loop, "_provider") and agent_loop._provider
                else None
            ),
        }
        return {"status": "healthy", "details": details}

    # -------------------------------------------------------------------------
    # Channel 操作（通过 Facade 风格封装）
    # -------------------------------------------------------------------------

    async def channel_list(self, bot_id: str | None = None) -> list[dict[str, Any]]:
        """列出通道。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_channels()

    async def channel_update(self, name: str, data: dict[str, Any], bot_id: str | None = None) -> dict[str, Any]:
        """更新通道配置。"""
        state = self._state_manager.get_state(bot_id)
        return await state.update_channel(name, data)

    async def channel_refresh(self, name: str | None = None, bot_id: str | None = None) -> list[dict[str, Any]]:
        """刷新通道。"""
        state = self._state_manager.get_state(bot_id)
        if name:
            result = await state.refresh_channel(name)
            return [result]
        return await state.refresh_all_channels()

    # -------------------------------------------------------------------------
    # Session 操作（通过 Facade 风格封装）
    # -------------------------------------------------------------------------

    async def session_list(self, bot_id: str | None = None) -> list[dict[str, Any]]:
        """列出会话。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_sessions()

    async def session_get(self, key: str, bot_id: str | None = None) -> dict[str, Any] | None:
        """获取会话详情。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_session(key)

    async def session_create(self, key: str | None = None, bot_id: str | None = None) -> dict[str, Any]:
        """创建会话。"""
        state = self._state_manager.get_state(bot_id)
        return await state.create_session(key)

    async def session_delete(self, key: str, bot_id: str | None = None) -> bool:
        """删除会话。"""
        state = self._state_manager.get_state(bot_id)
        return await state.delete_session(key)

    # -------------------------------------------------------------------------
    # Config 操作（通过 Facade 风格封装）
    # -------------------------------------------------------------------------

    async def config_get(self, bot_id: str | None = None) -> dict[str, Any]:
        """获取配置。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_config()

    async def config_update(self, section: str, data: dict[str, Any], bot_id: str | None = None) -> dict[str, Any]:
        """更新配置。"""
        state = self._state_manager.get_state(bot_id)
        return await state.update_config(section, data)

    async def config_schema(self, bot_id: str | None = None) -> dict[str, Any]:
        """获取配置 Schema。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_config_schema()

    async def config_validate(self, data: dict[str, Any], bot_id: str | None = None) -> dict[str, Any]:
        """验证配置。"""
        state = self._state_manager.get_state(bot_id)
        return await state.validate_config(data)

    # -------------------------------------------------------------------------
    # Queue 操作（通过 Facade 风格封装）
    # -------------------------------------------------------------------------

    async def queue_status(self, bot_id: str | None = None) -> dict[str, Any]:
        """获取队列状态。"""
        state = self._state_manager.get_state(bot_id)
        return await state.get_queue_status()

    async def queue_status_all(self) -> list[dict[str, Any]]:
        """获取所有 Bot 的队列状态。"""
        return await self._state_manager.get_all_queue_status()

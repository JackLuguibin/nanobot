"""
facade/bot/manager.py - BotFacade

Bot 生命周期管理接口。
设计原则：
- Bot 级别操作（创建/删除/启停）
- 需要操作 BotRegistry 和 BotStateManager
- 不涉及单个 Bot 内部组件管理
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class BotFacade(BaseManager[dict[str, Any]]):
    """
    Bot 生命周期管理门面。

    职责：
    - Bot 列表、创建、删除、启停
    - BotRegistry 操作
    - BotStateManager 操作

    设计原则：
    - 聚合多个 nanobot 组件（Registry + State）
    - 涉及运行时变更（启动/停止）
    """

    def __init__(
        self,
        bot_id: str | None = None,
        state_manager: Any = None,
        registry: Any = None,
    ) -> None:
        # BotFacade 特殊：无 bot_id 概念，管理所有 bot
        super().__init__(bot_id or "_system")
        self._state_manager = state_manager
        self._registry = registry

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有 Bot。"""
        registry = self._get_registry()
        manager = self._get_state_manager()
        default_id = registry.default_bot_id if registry else None

        bots = []
        for bot in (registry.list_bots() if registry else []):
            running = False
            if manager and manager.has_state(bot.id):
                running = manager.get_state(bot.id).is_running
            bots.append({
                "id": bot.id,
                "name": bot.name,
                "config_path": bot.config_path,
                "workspace_path": bot.workspace_path,
                "created_at": bot.created_at,
                "updated_at": bot.updated_at,
                "is_default": (bot.id == default_id),
                "running": running,
            })
        return bots

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定 Bot 详情。"""
        registry = self._get_registry()
        manager = self._get_state_manager()
        bot = registry.get_bot(identifier) if registry else None
        if not bot:
            return None

        running = False
        if manager and manager.has_state(identifier):
            running = manager.get_state(identifier).is_running

        return {
            "id": bot.id,
            "name": bot.name,
            "config_path": bot.config_path,
            "workspace_path": bot.workspace_path,
            "created_at": bot.created_at,
            "updated_at": bot.updated_at,
            "is_default": (bot.id == (registry.default_bot_id if registry else None)),
            "running": running,
        }

    # -------------------------------------------------------------------------
    # 写操作
    # -------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> OperationResult:
        """创建新 Bot。"""
        from pathlib import Path
        from console.server.utils.bot_builder import _initialize_bot
        from console.server.extension.config_loader import load_bot_config
        from console.server.api.websocket import get_connection_manager

        registry = self._get_registry()
        manager = self._get_state_manager()
        if not registry or not manager:
            return OperationResult.error("Registry or StateManager not available")

        try:
            bot = registry.create_bot(data.get("name", "New Bot"), data.get("source_config", {}))

            config_path = Path(bot.config_path)
            if config_path.exists():
                config = load_bot_config(config_path)
                state = _initialize_bot(bot.id, config, config_path)
                manager.set_state(bot.id, state)
                if state.cron_service and state.agent_loop:
                    await state.cron_service.start()

            await get_connection_manager().broadcast_bots_update()

            self.notify(FacadeEvent(
                type=FacadeEventType.CREATED,
                resource_type="bot",
                resource_id=bot.id,
                bot_id=bot.id,
                data={"name": bot.name},
            ))
            return OperationResult.ok(f"Bot '{bot.name}' created", {"id": bot.id, "name": bot.name})
        except Exception as e:
            logger.error("Failed to create bot: {}", e)
            return OperationResult.error(f"Failed to create bot: {e}")

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新 Bot 信息（名称等）。"""
        registry = self._get_registry()
        if not registry:
            return OperationResult.error("Registry not available")

        bot = registry.get_bot(identifier)
        if not bot:
            return OperationResult.error(f"Bot '{identifier}' not found")

        if "name" in data:
            bot.name = data["name"]
            registry.save()

        self.notify(FacadeEvent(
            type=FacadeEventType.UPDATED,
            resource_type="bot",
            resource_id=identifier,
            bot_id=identifier,
            data=data,
        ))
        return OperationResult.ok(f"Bot '{identifier}' updated")

    async def delete(self, identifier: str) -> OperationResult:
        """删除 Bot。"""
        from console.server.api.websocket import get_connection_manager

        registry = self._get_registry()
        manager = self._get_state_manager()
        if not registry or not manager:
            return OperationResult.error("Registry or StateManager not available")

        remaining = registry.list_bots()
        if len(remaining) <= 1:
            return OperationResult.error("Cannot delete the last bot")

        bot = registry.get_bot(identifier)
        if not bot:
            return OperationResult.error(f"Bot '{identifier}' not found")

        old_state = manager.remove_state(identifier)
        if old_state:
            if old_state.cron_service:
                old_state.cron_service.stop()
            if old_state.agent_loop:
                try:
                    await old_state.stop_current_task()
                except Exception as e:
                    logger.debug("Failed to stop bot '{}': {}", identifier, e)

        registry.delete_bot(identifier)
        await get_connection_manager().broadcast_bots_update()

        self.notify(FacadeEvent(
            type=FacadeEventType.DELETED,
            resource_type="bot",
            resource_id=identifier,
            bot_id=self.bot_id,
        ))
        return OperationResult.ok(f"Bot '{identifier}' deleted")

    # -------------------------------------------------------------------------
    # 启停
    # -------------------------------------------------------------------------

    async def start(self, identifier: str) -> OperationResult:
        """启动 Bot。"""
        from pathlib import Path
        from console.server.utils.bot_builder import _initialize_bot
        from console.server.extension.config_loader import load_bot_config
        from console.server.api.websocket import get_connection_manager

        registry = self._get_registry()
        manager = self._get_state_manager()
        if not registry or not manager:
            return OperationResult.error("Registry or StateManager not available")

        bot = registry.get_bot(identifier)
        if not bot:
            return OperationResult.error(f"Bot '{identifier}' not found")

        if manager.has_state(identifier) and manager.get_state(identifier).is_running:
            return OperationResult.ok(f"Bot '{identifier}' already running")

        config_path = Path(bot.config_path)
        if not config_path.exists():
            return OperationResult.error(f"Config file not found: {config_path}")

        try:
            config = load_bot_config(config_path)
        except Exception as e:
            return OperationResult.error(f"Config load failed: {e}")

        try:
            state = _initialize_bot(identifier, config, config_path)
            if state.workspace:
                try:
                    from console.server.extension.agents import AgentManager
                    agent_manager = AgentManager(identifier, state.workspace)
                    await agent_manager.initialize()
                    state._agent_manager = agent_manager
                except Exception as e:
                    logger.warning("Failed to initialize AgentManager for bot '{}': {}", identifier, e)
            manager.set_state(identifier, state)
            if state.cron_service and state.agent_loop:
                await state.cron_service.start()
            logger.info("Started bot '{}'", identifier)

            await get_connection_manager().broadcast_bots_update()

            self.notify(FacadeEvent(
                type=FacadeEventType.STARTED,
                resource_type="bot",
                resource_id=identifier,
                bot_id=identifier,
            ))
            return OperationResult.ok(f"Bot '{identifier}' started")
        except Exception as e:
            logger.exception("Failed to start bot '{}'", identifier)
            return OperationResult.error(f"Failed to start bot: {e}")

    async def stop(self, identifier: str) -> OperationResult:
        """停止 Bot。"""
        from console.server.api.websocket import get_connection_manager

        registry = self._get_registry()
        manager = self._get_state_manager()
        if not registry or not manager:
            return OperationResult.error("Registry or StateManager not available")

        bot = registry.get_bot(identifier)
        if not bot:
            return OperationResult.error(f"Bot '{identifier}' not found")

        if not manager.has_state(identifier):
            return OperationResult.ok(f"Bot '{identifier}' already stopped")

        old_state = manager.remove_state(identifier)
        if old_state:
            if old_state.cron_service:
                old_state.cron_service.stop()
            if old_state.agent_loop:
                try:
                    await old_state.stop_current_task()
                except Exception as e:
                    logger.debug("Failed to stop bot '{}': {}", identifier, e)

        logger.info("Stopped bot '{}'", identifier)
        await get_connection_manager().broadcast_bots_update()

        self.notify(FacadeEvent(
            type=FacadeEventType.STOPPED,
            resource_type="bot",
            resource_id=identifier,
            bot_id=identifier,
        ))
        return OperationResult.ok(f"Bot '{identifier}' stopped")

    async def set_default(self, identifier: str) -> OperationResult:
        """设置默认 Bot。"""
        from console.server.api.websocket import get_connection_manager

        registry = self._get_registry()
        manager = self._get_state_manager()
        if not registry or not manager:
            return OperationResult.error("Registry or StateManager not available")

        if not registry.set_default(identifier):
            return OperationResult.error(f"Bot '{identifier}' not found")

        manager.default_bot_id = identifier
        await get_connection_manager().broadcast_bots_update()
        return OperationResult.ok(f"Default bot set to '{identifier}'")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查 Bot 系统状态。"""
        registry = self._get_registry()
        manager = self._get_state_manager()

        if not registry or not manager:
            return HealthCheckResult.unhealthy("Registry or StateManager not available")

        bots = registry.list_bots()
        running = sum(1 for b in bots if manager.has_state(b.id) and manager.get_state(b.id).is_running)

        details = {
            "total_bots": len(bots),
            "running_bots": running,
            "default_bot": registry.default_bot_id,
        }
        return HealthCheckResult.healthy(
            f"{running}/{len(bots)} bots running",
            details=details
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _get_registry(self):
        if self._registry:
            return self._registry
        try:
            from console.server.bot_registry import get_registry
            return get_registry()
        except Exception:
            return None

    def _get_state_manager(self):
        if self._state_manager:
            return self._state_manager
        try:
            from console.server.api.state import get_state_manager
            return get_state_manager()
        except Exception:
            return None

"""
facade/init.py - Facade 层初始化

在 main.py lifespan 中初始化所有 Facade Manager。
设计原则：
- Facade 层在 BotState 初始化完成后创建
- 每个 Bot 对应一个 StateFacade 实例
- BotFacade 是系统级单例（非 per-bot）
- 通过 BotStateManager 的生命周期管理
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from console.server.facade.agent.manager import AgentFacade
from console.server.facade.alert.manager import AlertFacade
from console.server.facade.bot.manager import BotFacade
from console.server.facade.channel.manager import ChannelFacade
from console.server.facade.config.loader import ConfigLoader
from console.server.facade.config.validator import ConfigValidator
from console.server.facade.cron.manager import CronFacade
from console.server.facade.env.manager import EnvFacade
from console.server.facade.memory.manager import MemoryFacade
from console.server.facade.mcp.manager import MCPFacade
from console.server.facade.plans.manager import PlansFacade
from console.server.facade.provider.manager import ProviderFacade
from console.server.facade.session.manager import SessionFacade
from console.server.facade.skill.manager import SkillFacade
from console.server.facade.state.manager import StateFacade
from console.server.facade.status.manager import StatusFacade
from console.server.facade.tools.manager import ToolsFacade
from console.server.facade.usage.manager import UsageFacade
from console.server.facade.workspace.manager import WorkspaceFacade
from console.server.gateway.adapter import GatewayAdapter
from console.server.extension.config_bridge import ConfigBridge
from console.server.extension.gateway_state import GatewayBridge

if TYPE_CHECKING:
    from console.server.api.state import BotState, BotStateManager


class FacadeManager:
    """
    Facade 层管理器。

    职责：
    - 为每个 Bot 创建并管理 StateFacade 实例
    - 持有所有 Facade Manager 引用
    - BotFacade 是系统级单例
    - 提供 Facade 层初始化和清理
    """

    def __init__(self) -> None:
        self._facades: dict[str, StateFacade] = {}
        self._bot_facade: BotFacade | None = None

    def initialize_for_bot(self, bot_state: "BotState") -> StateFacade:
        """
        为指定 Bot 初始化 Facade 层。
        在 BotState 初始化完成后调用。
        """
        bot_id = bot_state.bot_id

        if bot_id in self._facades:
            logger.debug("Facade already initialized for bot '{}'", bot_id)
            return self._facades[bot_id]

        # 创建 ConfigBridge
        config_path = bot_state.config_path
        config_bridge: ConfigBridge | None = None
        if config_path:
            try:
                config_bridge = ConfigBridge(Path(config_path))
            except Exception as e:
                logger.warning("Failed to create ConfigBridge for bot '{}': {}", bot_id, e)

        # 创建 Gateway 适配器
        gateway_adapter = GatewayAdapter()
        if bot_state.channel_manager:
            gateway_adapter.set_channel_manager(bot_state.channel_manager)

        gateway_bridge = GatewayBridge()
        gateway_bridge.set_adapter(gateway_adapter)

        # 创建各 Manager（per-bot）
        agent_facade = AgentFacade(
            bot_id=bot_id,
            agent_loop=bot_state.agent_loop,
            agent_manager=bot_state._agent_manager if hasattr(bot_state, "_agent_manager") else None,
        )

        channel_facade = ChannelFacade(
            bot_id=bot_id,
            channel_manager=bot_state.channel_manager,
            config_bridge=config_bridge,
        )

        session_facade = SessionFacade(
            bot_id=bot_id,
            session_manager=bot_state.session_manager,
        )

        cron_facade = CronFacade(
            bot_id=bot_id,
            cron_service=bot_state.cron_service,
        )

        provider_facade = ProviderFacade(
            bot_id=bot_id,
            config_bridge=config_bridge,
        )

        skill_facade = SkillFacade(
            bot_id=bot_id,
            workspace=bot_state.workspace,
            config_bridge=config_bridge,
        )

        alert_facade = AlertFacade(
            bot_id=bot_id,
            agent_loop=bot_state.agent_loop,
            cron_service=bot_state.cron_service,
        )

        status_facade = StatusFacade(
            bot_id=bot_id,
            agent_loop=bot_state.agent_loop,
            channel_manager=bot_state.channel_manager,
            session_manager=bot_state.session_manager,
            cron_service=bot_state.cron_service,
            config=bot_state.config,
        )

        tools_facade = ToolsFacade(
            bot_id=bot_id,
            tool_call_logs=bot_state.tool_call_logs,
        )

        workspace_facade = WorkspaceFacade(
            bot_id=bot_id,
            workspace=bot_state.workspace,
        )

        plans_facade = PlansFacade(bot_id=bot_id)

        usage_facade = UsageFacade(bot_id=bot_id)

        env_facade = EnvFacade(
            bot_id=bot_id,
            config_path=Path(config_path) if config_path else None,
        )

        mcp_facade = MCPFacade(
            bot_id=bot_id,
            agent_loop=bot_state.agent_loop,
        )

        memory_facade = MemoryFacade(
            bot_id=bot_id,
            workspace=bot_state.workspace,
        )

        # 创建 StateFacade 并关联所有 Manager
        state_facade = StateFacade(bot_id=bot_id)
        state_facade.set_agent_facade(agent_facade)
        state_facade.set_channel_facade(channel_facade)
        state_facade.set_session_facade(session_facade)
        state_facade.set_cron_facade(cron_facade)
        state_facade.set_gateway_bridge(gateway_bridge)

        # 关联扩展 Manager（通过扩展属性）
        state_facade._alert_facade = alert_facade
        state_facade._status_facade = status_facade
        state_facade._tools_facade = tools_facade
        state_facade._workspace_facade = workspace_facade
        state_facade._plans_facade = plans_facade
        state_facade._usage_facade = usage_facade
        state_facade._env_facade = env_facade
        state_facade._mcp_facade = mcp_facade
        state_facade._memory_facade = memory_facade

        self._facades[bot_id] = state_facade

        logger.info("Facade layer initialized for bot '{}'", bot_id)
        return state_facade

    def get_facade(self, bot_id: str) -> StateFacade | None:
        """获取指定 Bot 的 StateFacade。"""
        return self._facades.get(bot_id)

    def get_facade_or_default(self, bot_id: str | None, default_bot_id: str | None = None) -> StateFacade | None:
        """获取指定 Bot 的 StateFacade，若不存在则返回默认。"""
        bid = bot_id or default_bot_id
        if bid and bid in self._facades:
            return self._facades[bid]
        if self._facades:
            return next(iter(self._facades.values()))
        return None

    def get_bot_facade(self) -> BotFacade:
        """获取系统级 BotFacade（按需创建）。"""
        if self._bot_facade is None:
            self._bot_facade = BotFacade()
        return self._bot_facade

    def shutdown(self) -> None:
        """关闭所有 Facade，清理资源。"""
        for bot_id, facade in self._facades.items():
            logger.debug("Shutting down Facade for bot '{}'", bot_id)
        self._facades.clear()
        self._bot_facade = None
        logger.info("Facade layer shutdown complete")


# 全局单例
_facade_manager: FacadeManager | None = None


def get_facade_manager() -> FacadeManager:
    """获取全局 FacadeManager。"""
    global _facade_manager
    if _facade_manager is None:
        _facade_manager = FacadeManager()
    return _facade_manager


def initialize_facade_layer() -> None:
    """初始化 Facade 层（main.py lifespan 中调用）。"""
    from console.server.api.state import get_state_manager
    manager = get_facade_manager()
    state_mgr = get_state_manager()
    for bot_id in state_mgr.all_bot_ids():
        bot_state = state_mgr.get_state(bot_id)
        manager.initialize_for_bot(bot_state)
    logger.info("Facade layer initialized for {} bots", len(manager._facades))


def shutdown_facade_layer() -> None:
    """关闭 Facade 层（main.py lifespan shutdown 中调用）。"""
    manager = get_facade_manager()
    manager.shutdown()

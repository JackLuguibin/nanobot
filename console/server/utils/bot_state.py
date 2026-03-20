"""Bot state initialization and lifecycle management."""

from fastapi import FastAPI
from loguru import logger
from pathlib import Path

from console.server.api.state import get_state_manager
from console.server.bot_registry import get_registry
from console.server.extension.agents import AgentManager
from console.server.extension.config_loader import load_bot_config
from console.server.utils.bot_builder import _initialize_bot
from nanobot.config.loader import get_config_path, load_config


async def initialize_bot_state(app: FastAPI) -> None:
    """Initialize bot states from registry (multi-bot) or legacy config (single-bot)."""
    registry = get_registry()
    manager = get_state_manager()

    if registry.needs_migration():
        logger.info("Migrating legacy config to bot registry...")
        registry.migrate_legacy()

    bots = registry.list_bots()

    if not bots:
        config_path = get_config_path()
        if not config_path.exists():
            logger.warning("No bots and no config found, running in limited mode")
            return

        config = load_config()
        info = registry.create_bot("Default Bot", config.model_dump(by_alias=True))
        bots = [info]

    default_id = registry.default_bot_id

    for bot_info in bots:
        config_path = Path(bot_info.config_path)
        if not config_path.exists():
            logger.error(
                "Bot '{}' config file not found: {} — check registry or re-run migration",
                bot_info.id,
                config_path,
            )
            continue

        config = load_bot_config(config_path)

        state = _initialize_bot(bot_info.id, config, config_path)

        if state.workspace:
            agent_manager = AgentManager(bot_info.id, state.workspace)
            await agent_manager.initialize()
            state._agent_manager = agent_manager
            logger.info("AgentManager initialized for bot '{}'", bot_info.id)

        manager.set_state(bot_info.id, state)
        if state.cron_service and state.agent_loop:
            await state.cron_service.start()
        logger.info("Initialized bot '{}' ({})", bot_info.name, bot_info.id)

    manager.default_bot_id = default_id or (bots[0].id if bots else None)
    logger.info("Console server initialized with {} bot(s)", len(manager.all_bot_ids()))


async def shutdown_bot_state() -> None:
    """Stop all bot cron services on shutdown."""
    manager = get_state_manager()
    for state in manager.all_states().values():
        if state.cron_service:
            state.cron_service.stop()

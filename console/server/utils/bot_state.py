"""Bot state initialization and lifecycle management."""

from fastapi import FastAPI
from loguru import logger
from pathlib import Path

from console.server.api.state import get_state_manager
from console.server.bot_registry import get_registry
from console.server.extension.agents import AgentManager
from console.server.extension.config_loader import load_bot_config
from console.server.extension.zmq_bus import get_zmq_bus, shutdown_zmq_bus
from console.server.utils.bot_builder import _initialize_bot
from console.server.utils.proxy_env import normalize_proxy_env_urls
from nanobot.config.loader import get_config_path, load_config


async def initialize_bot_state(app: FastAPI) -> None:
    """Initialize bot states from registry (multi-bot) or legacy config (single-bot)."""
    normalize_proxy_env_urls()
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

    # Initialize the shared global ZeroMQBus once before any AgentManager starts.
    # All bots will share this same bus (single bind on ports 5555/5556).
    zmq_bus = get_zmq_bus()
    if not zmq_bus.is_initialized:
        await zmq_bus.initialize()
        logger.info("Global ZeroMQ Bus initialized (shared across all bots)")

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
    """Stop all bot cron services and AgentManagers, then shut down the global ZeroMQ bus."""
    manager = get_state_manager()

    # Shutdown all AgentManagers first (unregisters from the shared bus)
    for bot_id, state in manager.all_states().items():
        if state._agent_manager:
            try:
                await state._agent_manager.shutdown()
                logger.info("AgentManager shutdown for bot '{}'", bot_id)
            except Exception as e:
                logger.error("Error shutting down AgentManager for bot '{}': {}", bot_id, e)

    # Stop all cron services
    for state in manager.all_states().values():
        if state.cron_service:
            state.cron_service.stop()

    # Cancel background websocket tasks
    from console.server.websocket import get_room_manager
    room_manager = get_room_manager()
    await room_manager.shutdown()

    # Finally, shutdown the shared global ZeroMQ bus
    await shutdown_zmq_bus()

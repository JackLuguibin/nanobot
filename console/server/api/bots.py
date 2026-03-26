"""API routes for bot management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from console.server.api.state import get_state_manager
from console.server.api.websocket import get_connection_manager
from console.server.models.bots import BotCreateRequest, BotInfoResponse, SetDefaultRequest

router = APIRouter(prefix="/bots")


def _resolve_state(bot_id: str | None = None):
    from console.server.api.state import get_state
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _bot_to_response(bot, manager, registry) -> BotInfoResponse:
    running = False
    if manager.has_state(bot.id):
        running = manager.get_state(bot.id).is_running
    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=running,
    )


@router.get("", response_model=list[BotInfoResponse])
async def list_bots() -> list[BotInfoResponse]:
    """List all registered bots."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()
    default_id = registry.default_bot_id

    return [
        _bot_to_response(bot, manager, registry)
        for bot in registry.list_bots()
    ]


@router.get("/{bot_id}", response_model=BotInfoResponse)
async def get_bot(bot_id: str) -> BotInfoResponse:
    """Get a specific bot."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()
    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _bot_to_response(bot, manager, registry)


@router.post("", response_model=BotInfoResponse)
async def create_bot(request: BotCreateRequest) -> BotInfoResponse:
    """Create a new bot with independent config and workspace."""
    from console.server.bot_registry import get_registry
    from console.server.utils.bot_builder import _initialize_bot
    from nanobot.config.loader import load_config
    from pathlib import Path

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.create_bot(request.name, request.source_config)

    try:
        config = load_config(Path(bot.config_path))
        state = _initialize_bot(bot.id, config, Path(bot.config_path))
        manager.set_state(bot.id, state)
        if state.cron_service and state.agent_loop:
            await state.cron_service.start()
    except Exception as e:
        logger.warning("Created bot '{}' but failed to initialize: {}", bot.id, e)

    await get_connection_manager().broadcast_bots_update()

    return _bot_to_response(bot, manager, registry)


@router.delete("/{bot_id}")
async def delete_bot(bot_id: str) -> dict[str, str]:
    """Delete a bot and its workspace."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    remaining = registry.list_bots()
    if len(remaining) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last bot")

    old_state = manager.remove_state(bot_id)
    if old_state:
        if old_state.cron_service:
            old_state.cron_service.stop()
        if old_state.agent_loop:
            try:
                await old_state.stop_current_task()
            except Exception as e:
                logger.debug("Failed to stop current task on bot '{}': {}", bot_id, e)

    registry.delete_bot(bot_id)

    await get_connection_manager().broadcast_bots_update()

    return {"status": "deleted", "bot_id": bot_id}


@router.put("/default")
async def set_default_bot(request: SetDefaultRequest) -> dict[str, str]:
    """Set the default bot."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    if not registry.set_default(request.bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")

    get_state_manager().default_bot_id = request.bot_id

    await get_connection_manager().broadcast_bots_update()

    return {"status": "ok", "default_bot_id": request.bot_id}


@router.post("/{bot_id}/start", response_model=BotInfoResponse)
async def start_bot(bot_id: str) -> BotInfoResponse:
    """Start (enable) a bot: load config, initialize state, and run."""
    from pathlib import Path

    from console.server.bot_registry import get_registry
    from console.server.extension.config_loader import load_bot_config
    from console.server.utils.bot_builder import _initialize_bot

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    if manager.has_state(bot_id) and manager.get_state(bot_id).is_running:
        state = manager.get_state(bot_id)
        return BotInfoResponse(
            id=bot.id,
            name=bot.name,
            config_path=bot.config_path,
            workspace_path=bot.workspace_path,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            is_default=(bot.id == registry.default_bot_id),
            running=True,
        )

    config_path = Path(bot.config_path)
    if not config_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Config file not found: {config_path}",
        )

    try:
        config = load_bot_config(config_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Config load failed: {e}") from e

    try:
        state = _initialize_bot(bot_id, config, config_path)
        if state.workspace:
            try:
                from console.server.extension.agents import AgentManager

                agent_manager = AgentManager(bot_id, state.workspace)
                await agent_manager.initialize()
                state._agent_manager = agent_manager
                logger.info("AgentManager initialized for bot '{}'", bot_id)
            except Exception as e:
                logger.warning("Failed to initialize AgentManager for bot '{}': {}", bot_id, e)
        manager.set_state(bot_id, state)
        if state.cron_service and state.agent_loop:
            await state.cron_service.start()
        logger.info("Started bot '{}' ({})", bot.name, bot_id)
    except Exception as e:
        logger.exception("Failed to start bot '{}'", bot_id)
        raise HTTPException(status_code=500, detail=str(e)) from e

    await get_connection_manager().broadcast_bots_update()

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=manager.get_state(bot_id).is_running,
    )


@router.post("/{bot_id}/stop", response_model=BotInfoResponse)
async def stop_bot(bot_id: str) -> BotInfoResponse:
    """Stop (disable) a bot: shutdown and remove its state. Bot remains in registry."""
    from console.server.bot_registry import get_registry

    registry = get_registry()
    manager = get_state_manager()

    bot = registry.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    if not manager.has_state(bot_id):
        return BotInfoResponse(
            id=bot.id,
            name=bot.name,
            config_path=bot.config_path,
            workspace_path=bot.workspace_path,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
            is_default=(bot.id == registry.default_bot_id),
            running=False,
        )

    old_state = manager.remove_state(bot_id)
    if old_state:
        if old_state.cron_service:
            old_state.cron_service.stop()
        if old_state.agent_loop:
            try:
                await old_state.stop_current_task()
            except Exception as e:
                logger.debug("Failed to stop current task on bot '{}': {}", bot_id, e)
    logger.info("Stopped bot '{}' ({})", bot.name, bot_id)

    await get_connection_manager().broadcast_bots_update()

    return BotInfoResponse(
        id=bot.id,
        name=bot.name,
        config_path=bot.config_path,
        workspace_path=bot.workspace_path,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        is_default=(bot.id == registry.default_bot_id),
        running=False,
    )

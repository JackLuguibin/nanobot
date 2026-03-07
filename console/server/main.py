"""FastAPI application entry point for the nanobot console server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from console.server.api import routes
from console.server.api.state import BotState, get_state_manager
from nanobot import __version__


def setup_logging() -> None:
    """Configure logging for the console server."""
    logger.remove()
    logger.add(
        "console/server/logs/console.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
    )
    logger.add(
        "console/server/logs/error.log",
        rotation="10 MB",
        retention="7 days",
        level="ERROR",
    )
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _make_provider(config) -> Any:
    """Create the appropriate LLM provider from config."""
    from nanobot.providers.custom_provider import CustomProvider
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from nanobot.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        raise ValueError("No API key configured")

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def _initialize_bot(bot_id: str, config, config_path: Path) -> BotState:
    """Create a BotState from a loaded Config object."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import sync_workspace_templates

    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = get_data_dir() / "cron" / f"jobs_{bot_id}.json"
    cron = CronService(cron_store_path)

    provider = None
    try:
        provider = _make_provider(config)
    except Exception as e:
        logger.warning("Bot '{}': failed to create provider: {}", bot_id, e)

    agent_loop: AgentLoop | None = None
    if provider is not None:
        try:
            agent_loop = AgentLoop(
                bus=bus,
                provider=provider,
                workspace=config.workspace_path,
                model=config.agents.defaults.model,
                temperature=config.agents.defaults.temperature,
                max_tokens=config.agents.defaults.max_tokens,
                max_iterations=config.agents.defaults.max_tool_iterations,
                memory_window=config.agents.defaults.memory_window,
                reasoning_effort=config.agents.defaults.reasoning_effort,
                brave_api_key=config.tools.web.search.api_key or None,
                web_proxy=config.tools.web.proxy or None,
                exec_config=config.tools.exec,
                cron_service=cron,
                restrict_to_workspace=config.tools.restrict_to_workspace,
                session_manager=session_manager,
                mcp_servers=config.tools.mcp_servers,
                channels_config=config.channels,
            )
        except Exception as e:
            logger.warning("Bot '{}': failed to create agent loop: {}", bot_id, e)

    channel_manager = None
    try:
        channel_manager = ChannelManager(config, bus)
    except Exception as e:
        logger.warning("Bot '{}': failed to create channel manager: {}", bot_id, e)

    config_dict = config.model_dump(by_alias=True) if hasattr(config, "model_dump") else {}

    state = BotState(bot_id=bot_id)
    state.initialize(
        agent_loop=agent_loop,
        session_manager=session_manager,
        channel_manager=channel_manager,
        config=config_dict,
        config_path=config_path,
        workspace=config.workspace_path,
    )
    return state


async def initialize_bot_state(app: FastAPI) -> None:
    """Initialize bot states from registry (multi-bot) or legacy config (single-bot)."""
    from console.server.bot_registry import get_registry
    from nanobot.config.loader import get_config_path, load_config

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

        try:
            config = load_config()
        except Exception as e:
            logger.warning("Failed to load config: {}", e)
            return

        info = registry.create_bot("Default Bot", config.model_dump(by_alias=True))
        bots = [info]

    default_id = registry.default_bot_id

    for bot_info in bots:
        try:
            config = load_config(Path(bot_info.config_path))
            state = _initialize_bot(bot_info.id, config, Path(bot_info.config_path))
            manager.set_state(bot_info.id, state)
            logger.info("Initialized bot '{}' ({})", bot_info.name, bot_info.id)
        except Exception as e:
            logger.error("Failed to initialize bot '{}': {}", bot_info.id, e)

    manager.default_bot_id = default_id or (bots[0].id if bots else None)
    logger.info("Console server initialized with {} bot(s)", len(manager.all_bot_ids()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    logger.info(f"Starting nanobot console v{__version__}")

    await initialize_bot_state(app)

    yield

    logger.info("Shutting down nanobot console")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Nanobot Console API",
        description="Web console for managing nanobot",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    setup_cors(app)

    app.include_router(routes.router)

    web_dist = Path(__file__).parent.parent / "web" / "dist"

    if web_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the SPA index.html for all non-API routes."""
            if full_path.startswith("api/"):
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(str(web_dist / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "console.server.main:app",
        host="0.0.0.0",
        port=18791,
        reload=True,
    )

"""FastAPI application entry point for the nanobot console server."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from console.server.api import routes
from console.server.api import routes_agents
from console.server.api.state import BotState, get_state_manager
from console.server.extension.agents import AgentManager
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

    if provider_name == "azure_openai":
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        if p and p.api_key and p.api_base:
            return AzureOpenAIProvider(
                api_key=p.api_key,
                api_base=p.api_base,
                default_model=model,
            )
        logger.warning("Azure OpenAI requires api_key and api_base in config")

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
    from dotenv import load_dotenv

    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import sync_workspace_templates

    env_path = config_path.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    sync_workspace_templates(config.workspace_path)

    raw_config_json = {}
    if config_path.exists():
        try:
            raw_config_json = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = config_path.parent / "cron" / "jobs.json"
    cron_store_path.parent.mkdir(parents=True, exist_ok=True)
    cron = CronService(cron_store_path)

    provider = None
    try:
        provider = _make_provider(config)
    except Exception as e:
        logger.warning("Bot '{}': failed to create provider: {}", bot_id, e)

    if provider is not None:
        from console.server.extension.usage import UsageTrackingProvider

        provider = UsageTrackingProvider(provider, bot_id)

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

    if agent_loop is not None:
        from console.server.extension.skills import PatchedContextBuilder

        skills_config = raw_config_json.get("skills", {})
        agent_loop.context = PatchedContextBuilder(
            agent_loop.workspace,
            skills_config=skills_config,
        )

        # Patch SubagentManager for event callbacks
        from console.server.extension.subagent_events import patch_subagent_manager
        patch_subagent_manager(agent_loop)

        # Set cron callback to run jobs through the agent
        from nanobot.agent.tools.cron import CronTool
        from nanobot.cron.types import CronJob

        import time
        from console.server.extension.cron_history import append_cron_run

        async def on_cron_job(job: CronJob) -> str | None:
            reminder_note = (
                "[Scheduled Task] Timer finished.\n\n"
                f"Task '{job.name}' has been triggered.\n"
                f"Scheduled instruction: {job.payload.message}"
            )
            cron_tool = agent_loop.tools.get("cron")
            cron_token = None
            if isinstance(cron_tool, CronTool):
                cron_token = cron_tool.set_cron_context(True)
            start_ms = int(time.time() * 1000)
            try:
                response = await agent_loop.process_direct(
                    reminder_note,
                    session_key=f"cron:{job.id}",
                    channel=job.payload.channel or "console",
                    chat_id=job.payload.to or "web",
                )
                duration_ms = int(time.time() * 1000) - start_ms
                append_cron_run(bot_id, job.id, job.name, start_ms, "ok", duration_ms, None)
                return response
            except Exception as e:
                duration_ms = int(time.time() * 1000) - start_ms
                append_cron_run(bot_id, job.id, job.name, start_ms, "error", duration_ms, str(e))
                raise
            finally:
                if isinstance(cron_tool, CronTool) and cron_token is not None:
                    cron_tool.reset_cron_context(cron_token)

        cron.on_job = on_cron_job

        # Wrap tool registry to log tool calls to state and activity
        from console.server.extension.activity import wrap_tool_registry_for_logging

        wrap_tool_registry_for_logging(agent_loop.tools, bot_id)

    channel_manager = None
    try:
        channel_manager = ChannelManager(config, bus)
    except Exception as e:
        logger.warning("Bot '{}': failed to create channel manager: {}", bot_id, e)

    config_dict = config.model_dump(by_alias=True) if hasattr(config, "model_dump") else {}
    config_dict["skills"] = raw_config_json.get("skills", {})

    state = BotState(bot_id=bot_id)
    state.initialize(
        agent_loop=agent_loop,
        session_manager=session_manager,
        channel_manager=channel_manager,
        cron_service=cron,
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

            # Initialize AgentManager for multi-agent support
            if state.workspace:
                try:
                    from console.server.extension.agents import AgentManager

                    agent_manager = AgentManager(bot_info.id, state.workspace)
                    await agent_manager.initialize()
                    state._agent_manager = agent_manager
                    logger.info("AgentManager initialized for bot '{}'", bot_info.id)
                except Exception as e:
                    logger.warning("Failed to initialize AgentManager for bot '{}': {}", bot_info.id, e)

            manager.set_state(bot_info.id, state)
            if state.cron_service and state.agent_loop:
                await state.cron_service.start()
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
    manager = get_state_manager()
    for state in manager.all_states().values():
        if state.cron_service:
            state.cron_service.stop()


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
    app.include_router(routes_agents.router)

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

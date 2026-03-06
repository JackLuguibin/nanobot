"""FastAPI application entry point for the nanobot console server."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from nanobot import __version__
from console.server.api import models, routes, state, websocket
from console.server.api.state import BotState, get_state


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
    # Console output
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Make this configurable
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def initialize_bot_state(app: FastAPI) -> None:
    """Initialize the bot state with core components.
    
    This initializes all the core nanobot components needed for the console
    to function properly, including AgentLoop, SessionManager, and ChannelManager.
    """
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.config.loader import get_data_dir, get_config_path, load_config
    from nanobot.cron.service import CronService
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import sync_workspace_templates
    
    # Try to load config
    config_path = get_config_path()
    if not config_path.exists():
        logger.warning("Config not found at {}, running in limited mode", config_path)
        return
    
    try:
        config = load_config()
    except Exception as e:
        logger.warning("Failed to load config: {}", e)
        return
    
    # Sync workspace templates
    sync_workspace_templates(config.workspace_path)
    
    # Create core components
    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)
    
    # Create cron service
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    
    # Try to create provider
    provider = None
    try:
        provider = _make_provider(config)
    except Exception as e:
        logger.warning("Failed to create provider (no API key?): {}", e)
        logger.warning("Running in limited mode without AI agent")
    
    # Create agent loop
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
            logger.warning("Failed to create agent loop: {}", e)
            logger.warning("Running in limited mode without AI agent")
    
    # Create channel manager
    try:
        channel_manager = ChannelManager(config, bus)
    except Exception as e:
        logger.warning("Failed to create channel manager: {}", e)
        channel_manager = None
    
    # Get or create state and initialize it
    bot_state = get_state()
    
    config_dict = config.model_dump(by_alias=True) if hasattr(config, 'model_dump') else {}
    
    bot_state.initialize(
        agent_loop=agent_loop,
        session_manager=session_manager,
        channel_manager=channel_manager,
        config=config_dict,
        config_path=config_path,
        workspace=config.workspace_path,
    )
    
    logger.info("Console server initialized with core components")


def _make_provider(config) -> Any:
    """Create the appropriate LLM provider from config."""
    from nanobot.providers.custom_provider import CustomProvider
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging()
    logger.info(f"Starting nanobot console v{__version__}")
    
    # Initialize state
    await initialize_bot_state(app)
    
    yield
    
    # Shutdown
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
    
    # Setup CORS
    setup_cors(app)
    
    # Include API routes
    app.include_router(routes.router)
    
    # Serve frontend static files
    web_dist = Path(__file__).parent.parent / "web" / "dist"
    
    if web_dist.exists():
        # Mount static files directory
        app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="assets")
        
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the SPA index.html for all non-API routes."""
            # Check if it's an API route
            if full_path.startswith("api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            # Serve index.html for SPA routing
            return FileResponse(str(web_dist / "index.html"))
    
    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "console.server.main:app",
        host="0.0.0.0",
        port=18791,  # Different from gateway port 18790
        reload=True,
    )

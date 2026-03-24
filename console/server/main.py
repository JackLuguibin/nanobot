"""FastAPI application entry point for the nanobot console server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from console.server.api import routes
from console.server.websocket import ws_router
from console.server.api.response import (
    SuccessEnvelopeMiddleware,
    generic_exception_handler,
    http_exception_handler,
)
from console.server.api.state import get_state_manager
from console.server.utils.bot_state import initialize_bot_state, shutdown_bot_state
from console.server.utils.cors import setup_cors
from console.server.utils.logging import setup_logging
from nanobot import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    logger.info(f"Starting nanobot console v{__version__}")

    await initialize_bot_state(app)

    yield

    logger.info("Shutting down nanobot console")
    await shutdown_bot_state()


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

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.add_middleware(SuccessEnvelopeMiddleware)

    app.include_router(routes.router)
    app.include_router(ws_router)

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

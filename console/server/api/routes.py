"""API routes for the console server.

This module aggregates all route modules via sub-routers.
"""

from __future__ import annotations

from fastapi import APIRouter

from console.server.api.agents import router as agents_router
from console.server.api.activity import router as activity_router
from console.server.api.queue import router as queue_router
from console.server.api.bots import router as bots_router
from console.server.api.chat import router as chat_router
from console.server.api.config import router as config_router
from console.server.api.cron import router as cron_router
from console.server.api.plans import router as plans_router
from console.server.api.sessions import router as sessions_router
from console.server.api.skills import router as skills_router
from console.server.api.status import router as status_router
from console.server.api.workspace import router as workspace_router

router = APIRouter(prefix="/api/v1")

router.include_router(bots_router)
router.include_router(agents_router)
router.include_router(status_router)
router.include_router(sessions_router)
router.include_router(chat_router)
router.include_router(workspace_router)
router.include_router(config_router)
router.include_router(skills_router)
router.include_router(cron_router)
router.include_router(plans_router)
router.include_router(activity_router)
router.include_router(queue_router)

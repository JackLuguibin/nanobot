"""API routes for the console server.

This module aggregates all route modules via sub-routers.
"""

from __future__ import annotations

from fastapi import APIRouter

from console.server.api.agents import router as agents_router
from console.server.api.activity import router as activity_router
from console.server.api.env import router as env_router
from console.server.api.alerts import router as alerts_router
from console.server.api.bot_files import router as bot_files_router
from console.server.api.bots import router as bots_router
from console.server.api.channels import router as channels_router
from console.server.api.chat import router as chat_router
from console.server.api.config import router as config_router
from console.server.api.cron import router as cron_router
from console.server.api.health import router as health_router
from console.server.api.health import control_router
from console.server.api.memory import router as memory_router
from console.server.api.mcp import router as mcp_router
from console.server.api.plans import router as plans_router
from console.server.api.queue import router as queue_router
from console.server.api.sessions import router as sessions_router
from console.server.api.skills import router as skills_router
from console.server.api.status import router as status_router
from console.server.api.health import router as health_router
from console.server.api.health import control_router
from console.server.api.tools import router as tools_router
from console.server.api.usage import router as usage_router
from console.server.api.workspace import router as workspace_router

router = APIRouter(prefix="/api/v1")

router.include_router(bots_router)
router.include_router(usage_router)
router.include_router(channels_router)
router.include_router(mcp_router)
router.include_router(tools_router)
router.include_router(alerts_router)
router.include_router(agents_router)
router.include_router(memory_router)
router.include_router(bot_files_router)
router.include_router(status_router)
router.include_router(sessions_router)
router.include_router(chat_router)
router.include_router(workspace_router)
router.include_router(config_router)
router.include_router(skills_router)
router.include_router(cron_router)
router.include_router(plans_router)
router.include_router(activity_router)
router.include_router(env_router)
router.include_router(queue_router)
router.include_router(health_router)
router.include_router(control_router)

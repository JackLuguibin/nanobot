"""Bot initialization logic for the console server."""

import json
import time
from pathlib import Path

from dotenv import load_dotenv

from console.server.api.state import BotState
from console.server.utils.provider import _make_provider
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.cron import CronTool
from nanobot.bus.queue import MessageBus
from nanobot.channels.manager import ChannelManager
from nanobot.cron.service import CronService
from nanobot.cron.types import CronJob
from nanobot.session.manager import SessionManager
from nanobot.utils.helpers import sync_workspace_templates


def _initialize_bot(bot_id: str, config, config_path: Path) -> BotState:
    """Create a BotState from a loaded Config object."""
    env_path = config_path.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    sync_workspace_templates(config.workspace_path)

    raw_config_json = {}
    if config_path.exists():
        raw_config_json = json.loads(config_path.read_text(encoding="utf-8"))

    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = config_path.parent / "cron" / "jobs.json"
    cron_store_path.parent.mkdir(parents=True, exist_ok=True)
    cron = CronService(cron_store_path)

    provider = _make_provider(config)

    from console.server.extension.usage import UsageTrackingProvider

    provider = UsageTrackingProvider(provider, bot_id)

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    _patch_agent_loop(agent_loop, bot_id, raw_config_json, cron)

    channel_manager = ChannelManager(config, bus)

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


def _patch_agent_loop(agent_loop: AgentLoop, bot_id: str, raw_config_json: dict, cron: CronService) -> None:
    """Apply all console-specific patches to an AgentLoop instance."""
    from console.server.extension.activity import wrap_tool_registry_for_logging
    from console.server.extension.cron_history import append_cron_run
    from console.server.extension.message_source import patch_agent_loop_message_source
    from console.server.extension.plans_skill import patch_plans_skill
    from console.server.extension.plans_tool import PlansTool
    from console.server.extension.skills import PatchedContextBuilder
    from console.server.extension.subagent_events import patch_subagent_manager

    skills_config = raw_config_json.get("skills", {})
    agent_loop.context = PatchedContextBuilder(agent_loop.workspace, skills_config=skills_config)

    if agent_loop.workspace:
        patch_plans_skill(agent_loop.workspace)

    patch_subagent_manager(agent_loop)
    patch_agent_loop_message_source(agent_loop)

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

    agent_loop.tools.register(PlansTool())

    wrap_tool_registry_for_logging(agent_loop.tools, bot_id)

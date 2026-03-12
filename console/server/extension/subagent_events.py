"""Extension to patch SubagentManager for event callbacks."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


async def _emit(subagent_mgr: "SubagentManager", event: dict[str, Any]) -> None:
    """Call the current event callback if set (used by patched methods)."""
    callback = getattr(subagent_mgr, "_event_callback", None)
    if not callback:
        return
    try:
        res = callback(event)
        if asyncio.iscoroutine(res):
            await res
    except Exception as e:
        logger.warning("Subagent event callback failed: {}", e)


def patch_subagent_manager(agent_loop) -> None:
    """Patch the SubagentManager to support event callbacks.

    Uses a stored callback (_event_callback) so that set_subagent_callback()
    can set it per-request. Events use 'subagent_id' to match frontend StreamChunk.
    """
    if not hasattr(agent_loop, "subagents") or agent_loop.subagents is None:
        logger.warning("AgentLoop has no subagents to patch")
        return

    subagent_mgr: SubagentManager = agent_loop.subagents  # type: ignore
    subagent_mgr._event_callback = None  # type: ignore[attr-defined]

    original_run = subagent_mgr._run_subagent
    original_announce = subagent_mgr._announce_result

    async def patched_run_subagent(
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        await _emit(
            subagent_mgr,
            {
                "type": "subagent_start",
                "subagent_id": task_id,
                "label": label,
                "task": task,
            },
        )
        await original_run(task_id, task, label, origin)

    async def patched_announce_result(
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        await _emit(
            subagent_mgr,
            {
                "type": "subagent_done",
                "subagent_id": task_id,
                "label": label,
                "task": task,
                "result": result,
                "status": status,
            },
        )
        await original_announce(task_id, label, task, result, origin, status)

    subagent_mgr._run_subagent = patched_run_subagent  # type: ignore[method-assign]
    subagent_mgr._announce_result = patched_announce_result

    logger.info("Patched SubagentManager with event callback support")


def set_subagent_callback(
    agent_loop, callback: Callable[[dict[str, Any]], None] | None
) -> None:
    """Set or update the subagent event callback (e.g. per chat stream request)."""
    if hasattr(agent_loop, "subagents") and agent_loop.subagents is not None:
        agent_loop.subagents._event_callback = callback  # type: ignore[attr-defined]
    else:
        logger.warning("AgentLoop has no subagents to set callback")

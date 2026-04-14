"""Session execution FSM and CPU-style interrupt helpers for the agent loop."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from enum import Enum
from typing import AsyncIterator, Awaitable, Callable


class ExecutionPhase(str, Enum):
    """High-level phase for one chat session (effective session key)."""

    IDLE = "idle"
    TURN_RUNNING = "turn_running"
    LLM_STREAMING = "llm_streaming"
    TOOL_EXECUTING = "tool_executing"
    HANDLING_INTERRUPT = "handling_interrupt"


class InterruptKind(str, Enum):
    """Logical interrupt sources (for logging / future vector table)."""

    STOP = "stop"
    SHUTDOWN = "shutdown"
    FOLLOWUP = "followup"


class MemorySubsystemPhase(str, Enum):
    """Background memory work (consolidation / Dream), serialized vs agent turns when configured."""

    IDLE = "idle"
    CONSOLIDATING = "consolidating"
    DREAMING = "dreaming"


class SessionInterruptController:
    """Per-session execution phase, cooperative abort, and optional interrupt masking.

    *abort* is signaled via an :class:`asyncio.Event` per session; :class:`~nanobot.agent.runner.AgentRunner`
    polls it between iterations. Task cancellation remains the primary stop mechanism; the event allows
    faster cooperative exit inside the runner loop.
    """

    __slots__ = (
        "_phase",
        "_abort_events",
        "_interrupt_mask_depth",
        "_memory_phase",
        "_active_turn_count",
    )

    def __init__(self) -> None:
        self._phase: dict[str, ExecutionPhase] = {}
        self._abort_events: dict[str, asyncio.Event] = {}
        self._interrupt_mask_depth: dict[str, int] = {}
        self._memory_phase: MemorySubsystemPhase = MemorySubsystemPhase.IDLE
        self._active_turn_count: int = 0

    def effective_phase(self, session_key: str | None) -> ExecutionPhase:
        if not session_key:
            return ExecutionPhase.IDLE
        return self._phase.get(session_key, ExecutionPhase.IDLE)

    def _abort_event(self, session_key: str) -> asyncio.Event:
        ev = self._abort_events.get(session_key)
        if ev is None:
            ev = asyncio.Event()
            self._abort_events[session_key] = ev
        return ev

    def request_abort(self, session_key: str) -> None:
        self._abort_event(session_key).set()

    def clear_abort(self, session_key: str) -> None:
        self._abort_event(session_key).clear()

    def should_abort(self, session_key: str | None) -> bool:
        if not session_key:
            return False
        ev = self._abort_events.get(session_key)
        return bool(ev and ev.is_set())

    def interrupts_masked(self, session_key: str | None) -> bool:
        if not session_key:
            return False
        return self._interrupt_mask_depth.get(session_key, 0) > 0

    @asynccontextmanager
    async def interrupt_mask(self, session_key: str | None) -> AsyncIterator[None]:
        """CLI-style critical section: nested depth counter."""
        if not session_key:
            yield
            return
        d = self._interrupt_mask_depth.get(session_key, 0) + 1
        self._interrupt_mask_depth[session_key] = d
        try:
            yield
        finally:
            nd = d - 1
            if nd <= 0:
                self._interrupt_mask_depth.pop(session_key, None)
            else:
                self._interrupt_mask_depth[session_key] = nd

    def on_dispatch_begin(self, session_key: str) -> None:
        self._phase[session_key] = ExecutionPhase.TURN_RUNNING
        self.clear_abort(session_key)
        self._active_turn_count += 1

    def on_dispatch_end(self, session_key: str) -> None:
        self._phase[session_key] = ExecutionPhase.IDLE
        self.clear_abort(session_key)
        self._active_turn_count = max(0, self._active_turn_count - 1)

    def mark_llm_streaming(self, session_key: str | None) -> None:
        if session_key:
            self._phase[session_key] = ExecutionPhase.LLM_STREAMING

    def mark_tool_executing(self, session_key: str | None) -> None:
        if session_key:
            self._phase[session_key] = ExecutionPhase.TOOL_EXECUTING

    def mark_turn_running(self, session_key: str | None) -> None:
        if session_key:
            self._phase[session_key] = ExecutionPhase.TURN_RUNNING

    def any_turn_active(self) -> bool:
        """True while at least one session dispatch is in progress (this process/workspace)."""
        return self._active_turn_count > 0

    async def dispatch_stop(
        self,
        session_key: str,
        tasks: list[asyncio.Task[object]],
        cancel_subagents: Callable[[str], Awaitable[int]],
    ) -> tuple[int, int]:
        """ISR top-half: request cooperative abort, cancel dispatch tasks, cancel subagents.

        Returns (cancelled_task_count, subagent_cancel_count).
        """
        self._phase[session_key] = ExecutionPhase.HANDLING_INTERRUPT
        self.request_abort(session_key)
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_n = await cancel_subagents(session_key)
        # Real _dispatch tasks also call on_dispatch_end (idle + clear_abort); fake tasks in tests do not.
        self.clear_abort(session_key)
        self._phase[session_key] = ExecutionPhase.IDLE
        return cancelled, sub_n

    def begin_memory_consolidating(self) -> None:
        self._memory_phase = MemorySubsystemPhase.CONSOLIDATING

    def end_memory_consolidating(self) -> None:
        self._memory_phase = MemorySubsystemPhase.IDLE

    def begin_dreaming(self) -> None:
        self._memory_phase = MemorySubsystemPhase.DREAMING

    def end_dreaming(self) -> None:
        self._memory_phase = MemorySubsystemPhase.IDLE

    @property
    def memory_phase(self) -> MemorySubsystemPhase:
        return self._memory_phase

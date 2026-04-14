"""Tests for session FSM / interrupt controller."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from nanobot.agent.interrupts import ExecutionPhase, SessionInterruptController


@pytest.mark.asyncio
async def test_dispatch_stop_clears_phase_for_fake_tasks() -> None:
    """Tasks that are not real _dispatch coroutines still leave the controller idle."""
    ctrl = SessionInterruptController()
    key = "test:c1"

    async def slow() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    t = asyncio.create_task(slow())
    await asyncio.sleep(0)
    await ctrl.dispatch_stop(key, [t], AsyncMock(return_value=0))
    assert ctrl.effective_phase(key) == ExecutionPhase.IDLE
    assert not ctrl.should_abort(key)


@pytest.mark.asyncio
async def test_dispatch_begin_end_turn_count() -> None:
    ctrl = SessionInterruptController()
    key = "cli:direct"
    assert not ctrl.any_turn_active()
    ctrl.on_dispatch_begin(key)
    assert ctrl.any_turn_active()
    assert ctrl.effective_phase(key) == ExecutionPhase.TURN_RUNNING
    ctrl.on_dispatch_end(key)
    assert not ctrl.any_turn_active()
    assert ctrl.effective_phase(key) == ExecutionPhase.IDLE


def test_mark_phases() -> None:
    ctrl = SessionInterruptController()
    k = "a:b"
    ctrl.on_dispatch_begin(k)
    ctrl.mark_llm_streaming(k)
    assert ctrl.effective_phase(k) == ExecutionPhase.LLM_STREAMING
    ctrl.mark_tool_executing(k)
    assert ctrl.effective_phase(k) == ExecutionPhase.TOOL_EXECUTING
    ctrl.mark_turn_running(k)
    assert ctrl.effective_phase(k) == ExecutionPhase.TURN_RUNNING


@pytest.mark.asyncio
async def test_interrupt_mask_nested_depth() -> None:
    ctrl = SessionInterruptController()
    k = "x:y"
    async with ctrl.interrupt_mask(k):
        assert ctrl.interrupts_masked(k)
        async with ctrl.interrupt_mask(k):
            assert ctrl.interrupts_masked(k)
        assert ctrl.interrupts_masked(k)
    assert not ctrl.interrupts_masked(k)

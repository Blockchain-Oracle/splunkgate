"""Behavioral + async tests for splunkgate_core.trace ContextVar propagation."""

import asyncio
from uuid import UUID

from splunkgate_core.trace import (
    current_trace_id,
    new_trace_id,
    trace_context,
)


def test_new_trace_id_returns_uuid() -> None:
    tid = new_trace_id()
    assert isinstance(tid, UUID)


def test_current_trace_id_is_none_outside_context() -> None:
    assert current_trace_id() is None


def test_sync_trace_context_sets_and_resets() -> None:
    tid = new_trace_id()
    assert current_trace_id() is None
    with trace_context(tid):
        assert current_trace_id() == tid
    assert current_trace_id() is None


def test_nested_trace_context_restores_outer_on_exit() -> None:
    outer = new_trace_id()
    inner = new_trace_id()
    with trace_context(outer):
        assert current_trace_id() == outer
        with trace_context(inner):
            assert current_trace_id() == inner
        assert current_trace_id() == outer
    assert current_trace_id() is None


async def test_async_trace_context_propagates_across_await() -> None:
    tid = new_trace_id()
    with trace_context(tid):
        assert current_trace_id() == tid
        await asyncio.sleep(0)
        assert current_trace_id() == tid


async def test_concurrent_async_tasks_remain_isolated() -> None:
    """Two concurrent tasks each see their own trace_id (no cross-task leak)."""
    seen: dict[str, UUID | None] = {}

    async def task(name: str, tid: UUID) -> None:
        with trace_context(tid):
            await asyncio.sleep(0.01)
            seen[name] = current_trace_id()

    a, b = new_trace_id(), new_trace_id()
    await asyncio.gather(task("a", a), task("b", b))
    assert seen["a"] == a
    assert seen["b"] == b
    assert current_trace_id() is None

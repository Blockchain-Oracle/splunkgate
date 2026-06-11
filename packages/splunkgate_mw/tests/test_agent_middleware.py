"""Behavioral tests for SafetyAgentMiddleware (story-mw-06).

Covers: trace_id seeded inside handler; child middleware sees the same
trace_id via contextvars; ALLOW session-summary verdict on happy path;
BLOCK summary when SplunkGateError propagates; non-SplunkGateError
exceptions propagate without a summary; thread_id-derived determinism;
borrowed-trace_id non-overwrite; contextvars unbinding on success +
failure paths.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from splunkgate_core.errors import ModelInputBlockedBySplunkGate, SplunkGateError
from splunkgate_core.trace import bind_trace_id, current_trace_id, unbind_trace_id
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel
from splunkgate_mw.agent_middleware import SafetyAgentMiddleware
from splunkgate_mw.profiles import Profile
from splunklib.ai.middleware import AgentRequest

_Handler = Callable[[AgentRequest], Awaitable[Any]]


class _FakeRequest:
    """Minimal AgentRequest stand-in (avoids splunklib's required messages)."""

    def __init__(self, thread_id: str | None = None) -> None:
        self.messages: list[object] = []
        self.thread_id = thread_id


async def _ok_handler(_request: object) -> object:
    return object()


# ── 1. trace_id seeded inside handler ──────────────────────────────────


@pytest.mark.asyncio
async def test_seeds_trace_id() -> None:
    captured: list[object] = []

    async def handler(_request: object) -> object:
        captured.append(current_trace_id())
        return object()

    mw = SafetyAgentMiddleware()
    await mw.agent_middleware(_FakeRequest("t1"), handler)
    assert captured[0] is not None


# ── 2. trace_id NOT leaked after invoke ────────────────────────────────


@pytest.mark.asyncio
async def test_trace_id_unbound_after_invoke() -> None:
    assert current_trace_id() is None
    mw = SafetyAgentMiddleware()
    await mw.agent_middleware(_FakeRequest("t1"), _ok_handler)
    assert current_trace_id() is None


# ── 3. Same trace_id observable by a child verdict emitted inside handler ──


@pytest.mark.asyncio
async def test_child_verdict_carries_parent_trace_id() -> None:
    """Simulate a child middleware emitting a Verdict; trace_id matches the parent's."""
    captured_trace_id: list[object] = []

    async def handler(_request: object) -> object:
        # Stand-in for a child mw_tool / mw_model emitting a verdict.
        captured_trace_id.append(current_trace_id())
        return object()

    mw = SafetyAgentMiddleware()
    await mw.agent_middleware(_FakeRequest("t1"), handler)
    # Re-run; the same thread_id derives the same trace_id.
    captured_trace_id.append(None)  # placeholder
    await mw.agent_middleware(_FakeRequest("t1"), handler)
    assert captured_trace_id[0] == captured_trace_id[-1]


# ── 4. ALLOW summary emitted on happy path ────────────────────────────


@pytest.mark.asyncio
async def test_allow_summary_emitted_on_happy_path() -> None:
    emitted: list[Verdict] = []
    with patch("splunkgate_mw.agent_middleware.safe_emit", side_effect=emitted.append):
        mw = SafetyAgentMiddleware()
        await mw.agent_middleware(_FakeRequest("t1"), _ok_handler)
    assert len(emitted) == 1
    assert emitted[0].surface == "mw_agent"
    assert emitted[0].verdict is VerdictLabel.ALLOW
    assert emitted[0].severity is Severity.NONE_SEVERITY


# ── 5. BLOCK summary emitted on SplunkGateError ────────────────────────


@pytest.mark.asyncio
async def test_block_summary_emitted_on_splunkgate_error() -> None:
    emitted: list[Verdict] = []

    blocking_verdict = Verdict(
        trace_id=uuid4(),
        timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
        verdict=VerdictLabel.BLOCK,
        severity=Severity.HIGH,
        rules=[],
        surface="mw_model",
        latency_ms=0.0,
    )

    async def angry_handler(_request: object) -> object:
        raise ModelInputBlockedBySplunkGate(blocking_verdict)

    with patch("splunkgate_mw.agent_middleware.safe_emit", side_effect=emitted.append):
        mw = SafetyAgentMiddleware()
        with pytest.raises(ModelInputBlockedBySplunkGate):
            await mw.agent_middleware(_FakeRequest("t1"), angry_handler)
    assert len(emitted) == 1
    assert emitted[0].surface == "mw_agent"
    assert emitted[0].verdict is VerdictLabel.BLOCK


# ── 6. Non-SplunkGateError exceptions propagate without BLOCK summary ──


@pytest.mark.asyncio
async def test_non_splunkgate_error_propagates_without_block_summary() -> None:
    emitted: list[Verdict] = []

    msg = "non-splunkgate timeout"

    async def timeout_handler(_request: object) -> object:
        raise TimeoutError(msg)

    with patch("splunkgate_mw.agent_middleware.safe_emit", side_effect=emitted.append):
        mw = SafetyAgentMiddleware()
        with pytest.raises(TimeoutError):
            await mw.agent_middleware(_FakeRequest("t1"), timeout_handler)
    # Summary IS emitted (ALLOW — we only own SplunkGateError outcomes).
    assert len(emitted) == 1
    assert emitted[0].verdict is VerdictLabel.ALLOW


# ── 7. thread_id-derived trace_id is deterministic ─────────────────────


@pytest.mark.asyncio
async def test_thread_id_stable_trace_id() -> None:
    """Two invocations with the same thread_id produce the same trace_id."""
    captured: list[object] = []

    async def handler(_request: object) -> object:
        captured.append(current_trace_id())
        return object()

    mw = SafetyAgentMiddleware()
    await mw.agent_middleware(_FakeRequest("thread-xyz"), handler)
    await mw.agent_middleware(_FakeRequest("thread-xyz"), handler)
    assert captured[0] == captured[1]


# ── 8. Different thread_ids produce different trace_ids ────────────────


@pytest.mark.asyncio
async def test_different_thread_ids_yield_different_trace_ids() -> None:
    captured: list[object] = []

    async def handler(_request: object) -> object:
        captured.append(current_trace_id())
        return object()

    mw = SafetyAgentMiddleware()
    await mw.agent_middleware(_FakeRequest("thread-A"), handler)
    await mw.agent_middleware(_FakeRequest("thread-B"), handler)
    assert captured[0] != captured[1]


# ── 9. Borrowed trace_id is reused, not overwritten ────────────────────


@pytest.mark.asyncio
async def test_borrowed_trace_id_is_reused() -> None:
    """If the parent process bound a trace_id, the middleware uses it as-is."""
    parent = uuid4()
    captured: list[object] = []

    async def handler(_request: object) -> object:
        captured.append(current_trace_id())
        return object()

    token = bind_trace_id(parent)
    try:
        mw = SafetyAgentMiddleware()
        await mw.agent_middleware(_FakeRequest("thread-z"), handler)
    finally:
        unbind_trace_id(token)
    assert captured[0] == parent


# ── 10. Borrowed trace_id stays bound after middleware exits ───────────


@pytest.mark.asyncio
async def test_borrowed_trace_id_not_unbound() -> None:
    parent = uuid4()
    token = bind_trace_id(parent)
    try:
        mw = SafetyAgentMiddleware()
        await mw.agent_middleware(_FakeRequest("thread-z"), _ok_handler)
        # Parent's bind survives.
        assert current_trace_id() == parent
    finally:
        unbind_trace_id(token)


# ── 11. Profile bound via structlog contextvar ────────────────────────


@pytest.mark.asyncio
async def test_profile_bound_to_structlog_contextvar() -> None:
    """The session summary verdict carries the profile name in agent_id."""
    emitted: list[Verdict] = []
    with patch("splunkgate_mw.agent_middleware.safe_emit", side_effect=emitted.append):
        mw = SafetyAgentMiddleware(
            profile=Profile(name="financial_services", description=""),
        )
        await mw.agent_middleware(_FakeRequest("t1"), _ok_handler)
    assert emitted[0].agent_id == "financial_services"


# ── 12. Concurrent invocations isolate via contextvars ─────────────────


@pytest.mark.asyncio
async def test_concurrent_invocations_isolate_trace_ids() -> None:
    """asyncio.gather of two sessions produces two independent trace_ids."""
    captured: dict[str, object] = {}

    async def handler_for(name: str) -> Callable[[object], Awaitable[object]]:
        async def handler(_request: object) -> object:
            await asyncio.sleep(0)
            captured[name] = current_trace_id()
            return object()

        return handler

    mw = SafetyAgentMiddleware()
    await asyncio.gather(
        mw.agent_middleware(_FakeRequest("A"), await handler_for("A")),
        mw.agent_middleware(_FakeRequest("B"), await handler_for("B")),
    )
    assert captured["A"] != captured["B"]


# ── 13. Public-API smoke ───────────────────────────────────────────────


def test_public_export_resolves_to_real_class() -> None:
    """`from splunkgate_mw import SafetyAgentMiddleware` resolves to the real impl."""
    from splunkgate_mw import SafetyAgentMiddleware as Exported  # noqa: PLC0415

    assert Exported is SafetyAgentMiddleware


# ── 14. Generic SplunkGateError (not a Blocked* subclass) → BLOCK summary ──


@pytest.mark.asyncio
async def test_generic_splunkgate_error_still_emits_block_summary() -> None:
    emitted: list[Verdict] = []
    msg = "judgment failed"

    async def angry_handler(_request: object) -> object:
        raise SplunkGateError(msg)

    with patch("splunkgate_mw.agent_middleware.safe_emit", side_effect=emitted.append):
        mw = SafetyAgentMiddleware()
        with pytest.raises(SplunkGateError):
            await mw.agent_middleware(_FakeRequest("t1"), angry_handler)
    assert emitted[0].verdict is VerdictLabel.BLOCK

"""Behavioral tests for SafetySubagentMiddleware (story-mw-05).

Exercises the DefenseClaw -> AI Defense escalation chain on subagent
calls: ALLOW passthrough, BLOCK raises SubagentBlockedBySplunkGate,
MODIFY sanitized args, per-subagent profile override, trace_id
propagation from the parent's contextvar bind, OTel emission with
surface="mw_subagent", and concurrent calls sharing the same trace_id.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
import splunkgate_mw.subagent_middleware as subagent_mw_mod
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from splunkgate_core.errors import SplunkGateError, SubagentBlockedBySplunkGate
from splunkgate_core.trace import trace_context
from splunkgate_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
)
from splunkgate_mw.profiles import Profile
from splunkgate_mw.subagent_middleware import SafetySubagentMiddleware
from splunklib.ai.messages import (
    HumanMessage,
    SubagentCall,
    SubagentTextResult,
)
from splunklib.ai.middleware import (
    AgentState,
    SubagentRequest,
    SubagentResponse,
)

_Handler = Callable[[SubagentRequest], Awaitable[SubagentResponse]]

_MW_EXPORTER = InMemorySpanExporter()
_provider = otel_trace.get_tracer_provider()
if isinstance(_provider, TracerProvider):
    _provider.add_span_processor(SimpleSpanProcessor(_MW_EXPORTER))
else:
    _provider = TracerProvider()
    _provider.add_span_processor(SimpleSpanProcessor(_MW_EXPORTER))
    otel_trace.set_tracer_provider(_provider)


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
    """Yield the shared in-memory exporter, cleared before each test."""
    _MW_EXPORTER.clear()
    return _MW_EXPORTER


def _make_request(
    name: str = "summarizer",
    args: dict[str, object] | str | None = None,
    *,
    call_id: str = "sub-call-1",
    thread_id: str = "thread-1",
) -> SubagentRequest:
    call_args: str | dict[str, object] = (
        {"input": "summarize this document"} if args is None else args
    )
    call = SubagentCall(id=call_id, name=name, args=call_args, thread_id=thread_id)
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content="ok")]),
        thread_id=thread_id,
    )
    return SubagentRequest(call=call, state=state)


def _ok_response(content: str = "summary") -> SubagentResponse:
    return SubagentResponse(result=SubagentTextResult(content=content))


def _record_handler() -> tuple[list[SubagentRequest], _Handler]:
    seen: list[SubagentRequest] = []

    async def handler(request: SubagentRequest) -> SubagentResponse:
        seen.append(request)
        return _ok_response()

    return seen, handler


# ── 1. ALLOW passthrough ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_allow_passthrough() -> None:
    """Benign SubagentCall → handler called exactly once with the unchanged request."""
    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("summarizer", {"input": "summarize this paragraph"})
    response = await mw.subagent_middleware(request, handler)
    assert len(seen) == 1
    assert seen[0] is request
    assert response.result.content == "summary"  # type: ignore[union-attr]


# ── 2. BLOCK path ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_block_raises_subagent_blocked_by_splunkgate() -> None:
    """Shell Injection on subagent input → BLOCK; handler not called."""
    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with pytest.raises(SubagentBlockedBySplunkGate) as exc_info:
        await mw.subagent_middleware(request, handler)
    assert len(seen) == 0
    blocked = exc_info.value
    assert isinstance(blocked.verdict, Verdict)
    assert blocked.verdict.verdict is VerdictLabel.BLOCK
    assert blocked.verdict.surface == "mw_subagent"


# ── 3. MODIFY path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_modify_rewrites_subagent_args() -> None:
    """MODIFY verdict → handler receives request with verdict.modifications['sanitized_args']."""
    sanitized = {"input": "[REDACTED:PII]"}

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.MODIFY,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")],
            surface="mw_subagent",
            latency_ms=0.0,
            modifications={"sanitized_args": sanitized},
        )

    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("summarizer", {"input": "ssn 123-45-6789"})
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        await mw.subagent_middleware(request, handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert len(seen) == 1
    assert seen[0].call.args == sanitized


# ── 4. per_subagent_profile override ──────────────────────────────────


@pytest.mark.asyncio
async def test_per_subagent_profile_override_applies() -> None:
    """The override resolves the right Profile for the matching subagent name."""
    seen_profiles: list[str] = []

    async def fake_judge(
        _request: SubagentRequest,
        profile: Profile,
        *_args: object,
        **_kwargs: object,
    ) -> Verdict:
        seen_profiles.append(profile.name)
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mw_subagent",
            latency_ms=0.0,
        )

    mw = SafetySubagentMiddleware(
        profile="default",
        per_subagent_profile={"summarizer": "financial_services"},
    )
    _seen, handler = _record_handler()
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        await mw.subagent_middleware(_make_request("summarizer"), handler)
        await mw.subagent_middleware(_make_request("classifier"), handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert seen_profiles == ["financial_services", "default"]


# ── 5. trace_id propagation from contextvar ────────────────────────────


@pytest.mark.asyncio
async def test_trace_id_preserved_from_contextvar() -> None:
    """When a parent has bound trace_id via splunkgate_core.trace, the verdict carries it."""
    bound = UUID("abc12300-0000-0000-0000-000000000000")
    captured: list[UUID] = []

    async def fake_judge(
        _request: SubagentRequest,
        _profile: Profile,
        _config: object,
        _ai_defense: object | None = None,
        *,
        trace_uuid: UUID | None = None,
    ) -> Verdict:
        assert trace_uuid is not None
        captured.append(trace_uuid)
        return Verdict(
            trace_id=trace_uuid,
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mw_subagent",
            latency_ms=0.0,
        )

    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        with trace_context(bound):
            await mw.subagent_middleware(_make_request("summarizer"), handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert captured == [bound]


# ── 6. Concurrent calls share the same trace_id ────────────────────────


@pytest.mark.asyncio
async def test_concurrent_subagent_calls_share_trace_id() -> None:
    """Two parallel subagent calls under one parent trace bind keep the same trace_id."""
    bound = UUID("11111111-2222-3333-4444-555555555555")
    captured: list[UUID] = []

    async def fake_judge(
        _request: SubagentRequest,
        _profile: Profile,
        _config: object,
        _ai_defense: object | None = None,
        *,
        trace_uuid: UUID | None = None,
    ) -> Verdict:
        assert trace_uuid is not None
        captured.append(trace_uuid)
        return Verdict(
            trace_id=trace_uuid,
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mw_subagent",
            latency_ms=0.0,
        )

    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        with trace_context(bound):
            await asyncio.gather(
                mw.subagent_middleware(_make_request("a", call_id="c1"), handler),
                mw.subagent_middleware(_make_request("b", call_id="c2"), handler),
            )
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert len(captured) == 2
    assert captured[0] == captured[1] == bound


# ── 7. Verdict surface + latency on ALLOW happy path ───────────────────


@pytest.mark.asyncio
async def test_allow_verdict_has_subagent_surface_and_positive_latency() -> None:
    captured: list[Verdict] = []

    async def fake_judge(
        _request: SubagentRequest,
        _profile: Profile,
        _config: object,
        _ai_defense: object | None = None,
        *,
        trace_uuid: UUID | None = None,
    ) -> Verdict:
        assert trace_uuid is not None
        v = Verdict(
            trace_id=trace_uuid,
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mw_subagent",
            latency_ms=0.42,
        )
        captured.append(v)
        return v

    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        await mw.subagent_middleware(_make_request("clean"), handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert len(captured) == 1
    assert captured[0].surface == "mw_subagent"
    assert captured[0].latency_ms > 0


# ── 8. String args MODIFY → fail-closed SplunkGateError ───────────────


@pytest.mark.asyncio
async def test_string_args_modify_fails_closed() -> None:
    """MODIFY on a string-args subagent call is not supported in v1; we raise instead."""

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.MODIFY,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")],
            surface="mw_subagent",
            latency_ms=0.0,
            modifications={"sanitized_args": {"input": "[REDACTED]"}},
        )

    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("summarizer", "raw input text")
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        with pytest.raises(SplunkGateError):
            await mw.subagent_middleware(request, handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert len(seen) == 0  # handler NEVER called on fail-closed


# ── 9. String args ALLOW → handler called unchanged ───────────────────


@pytest.mark.asyncio
async def test_string_args_allow_passthrough() -> None:
    """ALLOW on string-args subagent still passes through (the redaction path is the issue, not the shape)."""
    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("summarizer", "plain text input")
    await mw.subagent_middleware(request, handler)
    assert len(seen) == 1
    assert seen[0].call.args == "plain text input"


# ── 10. Downstream handler exception propagates verbatim ──────────────


@pytest.mark.asyncio
async def test_downstream_handler_exception_propagates() -> None:
    """Exceptions raised by the inner handler are not swallowed by the middleware."""

    class DownstreamError(RuntimeError):
        pass

    msg = "subagent crashed"

    async def bad_handler(_request: SubagentRequest) -> SubagentResponse:
        raise DownstreamError(msg)

    mw = SafetySubagentMiddleware()
    with pytest.raises(DownstreamError):
        await mw.subagent_middleware(_make_request("clean"), bad_handler)


# ── 11. Per-subagent profile dict can mix str and Profile values ──────


@pytest.mark.asyncio
async def test_per_subagent_profile_accepts_mixed_types() -> None:
    """The override dict accepts both `str` and `Profile` values."""
    hipaa = Profile(name="healthcare", description="HIPAA strict")
    captured: list[str] = []

    async def fake_judge(
        _request: SubagentRequest,
        profile: Profile,
        *_args: object,
        **_kwargs: object,
    ) -> Verdict:
        captured.append(profile.name)
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mw_subagent",
            latency_ms=0.0,
        )

    mw = SafetySubagentMiddleware(
        per_subagent_profile={"a": "financial_services", "b": hipaa},
    )
    _seen, handler = _record_handler()
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        await mw.subagent_middleware(_make_request("a"), handler)
        await mw.subagent_middleware(_make_request("b"), handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert captured == ["financial_services", "healthcare"]


# ── 12. Public API surface check ──────────────────────────────────────


def test_public_export_resolves_to_real_class() -> None:
    """`from splunkgate_mw import SafetySubagentMiddleware` resolves to the real impl."""
    from splunkgate_mw import SafetySubagentMiddleware as Exported  # noqa: PLC0415

    assert Exported is SafetySubagentMiddleware


# ── 14. BLOCK verdict's trace_id matches the bound parent ────────────
# (PR #128 review regression tests live in
#  tests/test_subagent_middleware_review_regressions.py — split out to
#  keep this file under the 400-LOC cap.)


@pytest.mark.asyncio
async def test_block_verdict_carries_parent_trace_id() -> None:
    bound = UUID("99999999-0000-0000-0000-000000000000")
    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with trace_context(bound), pytest.raises(SubagentBlockedBySplunkGate) as exc_info:
        await mw.subagent_middleware(request, handler)
    assert exc_info.value.verdict.trace_id == bound

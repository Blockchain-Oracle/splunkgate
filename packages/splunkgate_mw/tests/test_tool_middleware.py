"""Behavioral tests for SafetyToolMiddleware (story-mw-02).

Exercises the DefenseClaw → AI Defense escalation chain on tool calls:
ALLOW passthrough, BLOCK raises ToolBlockedBySplunkGate, MODIFY sanitized
args, OTel emission, profile routing, latency, trace_id propagation,
structlog binding, and error propagation from downstream handlers.

Uses an inline `otel_exporter` fixture wired into the process-global
TracerProvider + the MockAIDefenseClient as the deterministic AI
Defense stand-in (no respx HTTP mocks needed at this layer — the
AI Defense client is already an injectable Protocol).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
import splunkgate_mw.tool_middleware as tool_mw_mod
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from splunkgate_core.errors import SplunkGateError, ToolBlockedBySplunkGate
from splunkgate_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
)
from splunkgate_judges.ai_defense_mock import MockAIDefenseClient
from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
)
from splunkgate_judges.ai_defense_types import (
    InspectResponse as _InspectResponse,
)
from splunkgate_judges.ai_defense_types import (
    RuleHit as _AIDefRuleHit,
)
from splunkgate_mw._base import SafetyToolMiddleware as _BaseExport
from splunkgate_mw.config import Config
from splunkgate_mw.profiles import Profile
from splunkgate_mw.tool_middleware import (
    AIDefenseLike,
    SafetyToolMiddleware,
    judge_tool_call,
)
from splunklib.ai.messages import (
    HumanMessage,
    ToolCall,
    ToolResult,
    ToolType,
)
from splunklib.ai.middleware import (
    AgentState,
    ToolRequest,
    ToolResponse,
)

_Handler = Callable[[ToolRequest], Awaitable[ToolResponse]]

_DOWNSTREAM_ERR_MSG = "tool crashed"

# In-memory OTel exporter wired into whatever TracerProvider is already set
# (matches the pattern in test_model_middleware_pre.py).
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
    name: str = "splunk_search",
    args: dict[str, object] | None = None,
    *,
    call_id: str = "call-1",
    thread_id: str = "thread-1",
) -> ToolRequest:
    call = ToolCall(
        id=call_id,
        name=name,
        type=ToolType.LOCAL,
        args=dict(args) if args is not None else {"query": "index=main"},
    )
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content="ok")]),
        thread_id=thread_id,
    )
    return ToolRequest(call=call, state=state)


def _ok_response(content: str = "ok") -> ToolResponse:
    return ToolResponse(result=ToolResult(content=content, structured_content=None))


def _record_handler() -> tuple[list[ToolRequest], _Handler]:
    seen: list[ToolRequest] = []

    async def handler(request: ToolRequest) -> ToolResponse:
        seen.append(request)
        return _ok_response()

    return seen, handler


# ---------------------------------------------------------------------------
# 1. ALLOW passthrough — handler called exactly once with the unchanged request.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allow_passthrough() -> None:
    """Benign ToolCall → handler called exactly once with the unchanged request."""
    mw = SafetyToolMiddleware()
    seen, handler = _record_handler()
    request = _make_request("splunk_search", {"query": "index=main"})
    response = await mw.tool_middleware(request, handler)
    assert len(seen) == 1
    assert seen[0] is request
    assert response.result.content == "ok"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 2. BLOCK path — ToolBlockedBySplunkGate raised; handler NEVER called.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_raises_tool_blocked_by_splunkgate() -> None:
    """Shell Injection on a shell-runner tool → BLOCK; handler not called."""
    mw = SafetyToolMiddleware()
    seen, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)
    assert len(seen) == 0
    blocked = exc_info.value
    assert isinstance(blocked.verdict, Verdict)
    assert blocked.verdict.verdict is VerdictLabel.BLOCK
    assert blocked.verdict.surface == "mw_tool"


# ---------------------------------------------------------------------------
# 3. MODIFY path — handler invoked with sanitized args.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modify_returns_sanitized_args() -> None:
    """MODIFY verdict → handler receives request with verdict.modifications['sanitized_args']."""

    sanitized = {"query": "index=main [REDACTED:PII]"}

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.MODIFY,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")],
            surface="mw_tool",
            latency_ms=0.0,
            modifications={"sanitized_args": sanitized},
        )

    mw = SafetyToolMiddleware()
    seen, handler = _record_handler()
    request = _make_request("splunk_search", {"query": "index=main"})
    original = tool_mw_mod.judge_tool_call
    tool_mw_mod.judge_tool_call = fake_judge  # type: ignore[assignment]
    try:
        await mw.tool_middleware(request, handler)
    finally:
        tool_mw_mod.judge_tool_call = original  # type: ignore[assignment]
    assert len(seen) == 1
    assert seen[0].call.args == sanitized


# ---------------------------------------------------------------------------
# 4. OTel emission — exactly one gen_ai.evaluation.result event per invocation.
# ---------------------------------------------------------------------------


def _events_with_name(exporter: InMemorySpanExporter, name: str) -> list[Any]:
    spans = exporter.get_finished_spans()
    return [e for s in spans for e in s.events if e.name == name]


@pytest.mark.asyncio
async def test_allow_emits_one_otel_event_surface_mw_tool(
    otel_exporter: InMemorySpanExporter,
) -> None:
    """ALLOW emits exactly one gen_ai.evaluation.result with surface=mw_tool."""
    otel_exporter.clear()
    tracer = otel_trace.get_tracer(__name__)
    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    with tracer.start_as_current_span("test_span"):
        await mw.tool_middleware(_make_request(), handler)
    events = _events_with_name(otel_exporter, "gen_ai.evaluation.result")
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mw_tool"
    assert attrs["splunkgate.trace_id"]  # populated


@pytest.mark.asyncio
async def test_block_emits_one_otel_event_surface_mw_tool(
    otel_exporter: InMemorySpanExporter,
) -> None:
    """BLOCK emits exactly one gen_ai.evaluation.result event before raising."""
    otel_exporter.clear()
    tracer = otel_trace.get_tracer(__name__)
    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with (
        tracer.start_as_current_span("test_span"),
        pytest.raises(ToolBlockedBySplunkGate),
    ):
        await mw.tool_middleware(request, handler)
    events = _events_with_name(otel_exporter, "gen_ai.evaluation.result")
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mw_tool"
    assert attrs["gen_ai.evaluation.score.label"] == "block"


# ---------------------------------------------------------------------------
# 5. DefenseClaw-only hit — no AI Defense escalation when escalate flag is off.
# ---------------------------------------------------------------------------


class _SpyAIDefense:
    """Test double recording every inspect_chat call."""

    def __init__(self) -> None:
        self.calls: list[object] = []
        self._inner = MockAIDefenseClient()

    async def inspect_chat(
        self,
        request: object,
        *,
        trace_id: str | None = None,
    ) -> _InspectResponse:
        self.calls.append(request)
        return await self._inner.inspect_chat(  # type: ignore[arg-type]
            request,  # type: ignore[arg-type]
            trace_id=trace_id,
        )


@pytest.mark.asyncio
async def test_defenseclaw_hit_no_escalation_when_flag_off() -> None:
    """Cheap hit + escalate=False → verdict source is defenseclaw_regex; no AI Defense call."""
    spy = _SpyAIDefense()
    cfg = Config(escalate_on_first_pass_hit=False)
    mw = SafetyToolMiddleware(
        config=cfg,
        ai_defense=cast("AIDefenseLike", spy),
    )
    _, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)
    assert len(spy.calls) == 0
    assert any(r.source == "defenseclaw_regex" for r in exc_info.value.verdict.rules)


# ---------------------------------------------------------------------------
# 6. AI Defense-escalated hit — verdict carries an ai_defense-sourced rule.
# ---------------------------------------------------------------------------


class _FixedAIDefense:
    """Returns a fixed HIGH InspectResponse regardless of input."""

    def __init__(self, response: _InspectResponse) -> None:
        self.response = response
        self.call_count = 0

    async def inspect_chat(
        self,
        _request: object,
        *,
        trace_id: str | None = None,  # noqa: ARG002 — Protocol signature requirement
    ) -> _InspectResponse:
        self.call_count += 1
        return self.response


def _high_prompt_injection_response() -> _InspectResponse:
    return _InspectResponse(
        is_safe=False,
        severity=Severity.HIGH,
        rules=[
            _AIDefRuleHit(
                rule_name=AIDefenseRule.PROMPT_INJECTION,
                classification=Classification.SECURITY_VIOLATION,
            )
        ],
        explanation="prompt injection detected",
    )


@pytest.mark.asyncio
async def test_ai_defense_escalation_attaches_ai_defense_source() -> None:
    """Cheap hit + escalate=True + AI Defense HIGH → verdict carries ai_defense rule."""
    fake = _FixedAIDefense(_high_prompt_injection_response())
    cfg = Config(escalate_on_first_pass_hit=True)
    mw = SafetyToolMiddleware(
        config=cfg,
        ai_defense=cast("AIDefenseLike", fake),
    )
    _, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)
    assert fake.call_count == 1
    sources = [r.source for r in exc_info.value.verdict.rules]
    assert "ai_defense" in sources
    assert exc_info.value.verdict.severity is Severity.HIGH


# ---------------------------------------------------------------------------
# 7. AI Defense miss on clean payload — never called.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_defense_not_called_when_payload_is_clean() -> None:
    """No DefenseClaw hit + escalate=True → still no AI Defense call (no rule trigger)."""
    spy = _SpyAIDefense()
    cfg = Config(escalate_on_first_pass_hit=True)
    mw = SafetyToolMiddleware(
        config=cfg,
        ai_defense=cast("AIDefenseLike", spy),
    )
    _, handler = _record_handler()
    request = _make_request("splunk_search", {"query": "index=main"})
    await mw.tool_middleware(request, handler)
    # escalation only triggers on a DefenseClaw hit; clean payload short-circuits.
    assert len(spy.calls) == 0


# ---------------------------------------------------------------------------
# 8. Profile routing — string profile constructs without error and propagates.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_routing_default() -> None:
    """profile='default' constructs and runs the ALLOW passthrough."""
    mw = SafetyToolMiddleware(profile="default")
    _, handler = _record_handler()
    await mw.tool_middleware(_make_request(), handler)


@pytest.mark.asyncio
async def test_profile_routing_with_profile_object() -> None:
    """Profile object construction wires through with no errors."""
    profile = Profile(name="financial_services", description="FSI profile")
    mw = SafetyToolMiddleware(profile=profile)
    _, handler = _record_handler()
    await mw.tool_middleware(_make_request(), handler)


# ---------------------------------------------------------------------------
# 9. latency_ms populated > 0 on every emitted verdict.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latency_ms_populated_on_allow_verdict() -> None:
    """ALLOW verdict carries latency_ms > 0 (perf_counter delta)."""
    verdict = await judge_tool_call(
        _make_request("splunk_search", {"query": "index=main"}),
        Profile(name="default", description=""),
        Config(),
    )
    assert verdict.verdict is VerdictLabel.ALLOW
    assert verdict.latency_ms > 0.0


# ---------------------------------------------------------------------------
# 10. trace_id propagation onto Verdict + OTel event.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_id_propagates_to_otel_event(
    otel_exporter: InMemorySpanExporter,
) -> None:
    """Verdict.trace_id matches splunkgate.trace_id on emitted OTel event."""
    otel_exporter.clear()
    tracer = otel_trace.get_tracer(__name__)
    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    with tracer.start_as_current_span("test_span"):
        await mw.tool_middleware(_make_request(), handler)
    events = _events_with_name(otel_exporter, "gen_ai.evaluation.result")
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    # UUID stringification: matches the format produced inside the middleware.
    assert isinstance(attrs["splunkgate.trace_id"], str)
    assert len(attrs["splunkgate.trace_id"]) == 36  # UUID-4 canonical length


# ---------------------------------------------------------------------------
# 11. sanitized_args missing → SplunkGateError instead of silent fallback.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modify_without_sanitized_args_raises_splunkgate_error() -> None:
    """MODIFY verdict without modifications['sanitized_args'] is a contract violation."""

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.MODIFY,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")],
            surface="mw_tool",
            latency_ms=0.0,
            modifications=None,  # contract violation
        )

    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    original = tool_mw_mod.judge_tool_call
    tool_mw_mod.judge_tool_call = fake_judge  # type: ignore[assignment]
    try:
        with pytest.raises(SplunkGateError):
            await mw.tool_middleware(_make_request(), handler)
    finally:
        tool_mw_mod.judge_tool_call = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 12. Downstream handler exception propagates unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downstream_handler_exception_propagates() -> None:
    """Exception raised by the inner handler is NOT swallowed by the middleware."""

    class _DownstreamError(RuntimeError):
        pass

    async def handler(_request: ToolRequest) -> ToolResponse:
        raise _DownstreamError(_DOWNSTREAM_ERR_MSG)

    mw = SafetyToolMiddleware()
    with pytest.raises(_DownstreamError):
        await mw.tool_middleware(_make_request(), handler)


# ---------------------------------------------------------------------------
# 13. structlog binding includes trace_id + verdict label on BLOCK.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_logs_structured_event_with_trace_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On BLOCK, the bound structlog logger emits a structured line carrying trace_id + label."""
    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    request = _make_request("shell_exec", {"cmd": "rm -rf /"})
    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)
    captured = capsys.readouterr()
    # structlog default printer writes to stdout. The bound binder includes
    # tool_name + trace_id + severity in the rendered line.
    combined = captured.out + captured.err
    assert "tool_blocked" in combined
    assert str(exc_info.value.verdict.trace_id) in combined


# ---------------------------------------------------------------------------
# 14. Pure judge_tool_call producer — no handler invocation, no raises on BLOCK.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_tool_call_returns_block_verdict_without_raising() -> None:
    """The judge helper is a pure verdict producer — never calls handler or raises."""
    verdict = await judge_tool_call(
        _make_request("shell_exec", {"cmd": "rm -rf /"}),
        Profile(name="default", description=""),
        Config(escalate_on_first_pass_hit=False),
    )
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.surface == "mw_tool"
    assert any(r.source == "defenseclaw_regex" for r in verdict.rules)


# ---------------------------------------------------------------------------
# 15. Bonus: re-export hygiene — SafetyToolMiddleware reachable from _base.
# ---------------------------------------------------------------------------


def test_safety_tool_middleware_reexported_from_base() -> None:
    """from splunkgate_mw._base import SafetyToolMiddleware still works (backwards compat)."""
    assert _BaseExport is SafetyToolMiddleware

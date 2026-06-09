"""Regression tests for the PR #121 fix round (silent-failure shapes).

Covers the BLOCKING + IMPORTANT findings from the 4-reviewer toolkit
fleet on mw-02. These are the second batch of tests for SafetyToolMiddleware;
the happy-path / contract tests live in `test_tool_middleware.py`.

Findings exercised here:
  - B1: OTel exporter crash MUST NOT drop the BLOCK or the audit row.
  - B2: AI Defense exception MUST fail closed instead of propagating.
  - B3: _rewrite_request MUST reject empty sanitized_args for non-empty input.
  - I1: DefenseClaw backend exception MUST fail closed.
  - I4: AI Defense rule outside the v1 redactor map MUST force BLOCK
        (the PR #117 _redact silent-no-op shape).
  - End-to-end sanity tests for the existing MODIFY happy path so we'd
    catch regressions in the cheap-pass + sanitize chain.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
import splunkgate_mw._fail_closed as fail_closed_mod
import splunkgate_mw.tool_middleware as tool_mw_mod
from splunkgate_core.errors import SplunkGateError, ToolBlockedBySplunkGate
from splunkgate_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
)
from splunkgate_judges._errors import AIDefenseTimeoutError
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
from splunkgate_mw._sanitize import is_supported_rule
from splunkgate_mw.config import Config
from splunkgate_mw.tool_middleware import (
    AIDefenseLike,
    SafetyToolMiddleware,
)
from splunklib.ai.messages import (
    HumanMessage,
    ToolCall,
    ToolType,
)
from splunklib.ai.middleware import (
    AgentState,
    ToolRequest,
    ToolResponse,
)

_Handler = Callable[[ToolRequest], Awaitable[ToolResponse]]


def _make_request(
    name: str = "splunk_search",
    args: dict[str, object] | None = None,
) -> ToolRequest:
    call = ToolCall(
        id="call-1",
        name=name,
        type=ToolType.LOCAL,
        args=dict(args) if args is not None else {"query": "index=main"},
    )
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content="ok")]),
        thread_id="thread-1",
    )
    return ToolRequest(call=call, state=state)


def _record_handler() -> tuple[list[ToolRequest], _Handler]:
    seen: list[ToolRequest] = []

    async def handler(request: ToolRequest) -> ToolResponse:
        from splunklib.ai.messages import ToolResult  # noqa: PLC0415 — test fixture

        seen.append(request)
        return ToolResponse(result=ToolResult(content="ok", structured_content=None))

    return seen, handler


# ---------------------------------------------------------------------------
# B1. Exporter crash MUST NOT drop the BLOCK.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_verdict_event_exporter_crash_does_not_drop_block(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exporter RuntimeError MUST NOT swallow the BLOCK or drop the audit row.

    Per PR #116/#117 + the PR #121 fix round: emit_verdict_event is
    wrapped in safe_emit so an exporter crash WARN-and-continues; the
    middleware then proceeds to raise ToolBlockedBySplunkGate normally.
    """

    def boom(_verdict: Verdict) -> None:
        msg = "exporter is down"
        raise RuntimeError(msg)

    original = fail_closed_mod.emit_verdict_event
    fail_closed_mod.emit_verdict_event = boom  # type: ignore[assignment]
    try:
        mw = SafetyToolMiddleware()
        _, handler = _record_handler()
        request = _make_request("shell_exec", {"cmd": "rm -rf /"})
        with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
            await mw.tool_middleware(request, handler)
    finally:
        fail_closed_mod.emit_verdict_event = original  # type: ignore[assignment]

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    blocked = exc_info.value.verdict
    assert "otel.emit_failed" in combined
    assert str(blocked.trace_id) in combined
    assert blocked.verdict is VerdictLabel.BLOCK
    assert blocked.surface == "mw_tool"


# ---------------------------------------------------------------------------
# B2. AI Defense timeout fails closed to BLOCK with ai_defense_unavailable.
# ---------------------------------------------------------------------------


class _RaisingAIDefense:
    """Stand-in AIDefenseLike whose inspect_chat always raises a given exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.call_count = 0

    async def inspect_chat(
        self,
        _request: object,
        *,
        trace_id: str | None = None,  # noqa: ARG002 — Protocol signature requirement
    ) -> _InspectResponse:
        self.call_count += 1
        raise self._exc


@pytest.mark.asyncio
async def test_ai_defense_timeout_fails_closed_to_block() -> None:
    """AI Defense network timeout MUST NOT drop the audit row — fail closed instead."""
    fake = _RaisingAIDefense(AIDefenseTimeoutError("upstream timeout"))
    cfg = Config(escalate_on_first_pass_hit=True)
    mw = SafetyToolMiddleware(
        config=cfg,
        ai_defense=cast("AIDefenseLike", fake),
    )
    _, handler = _record_handler()
    request = _make_request("store_note", {"text": "user ssn is 123-45-6789"})

    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)

    assert fake.call_count == 1
    verdict = exc_info.value.verdict
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.severity is Severity.MEDIUM
    rule_names = [r.rule for r in verdict.rules]
    assert "PII" in rule_names
    assert "ai_defense_unavailable" in rule_names
    synthetic = next(r for r in verdict.rules if r.rule == "ai_defense_unavailable")
    assert synthetic.source == "defenseclaw_regex"


# ---------------------------------------------------------------------------
# I1. DefenseClaw backend exception fails closed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_defenseclaw_backend_exception_fails_closed() -> None:
    """A RuntimeError from evaluate_tool_call MUST fail closed to BLOCK."""

    async def boom(_name: str, _args: dict[str, object]) -> None:
        msg = "regex compile error"
        raise RuntimeError(msg)

    original = fail_closed_mod.evaluate_tool_call
    fail_closed_mod.evaluate_tool_call = boom  # type: ignore[assignment]
    try:
        mw = SafetyToolMiddleware()
        _, handler = _record_handler()
        request = _make_request("store_note", {"text": "anything"})
        with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
            await mw.tool_middleware(request, handler)
    finally:
        fail_closed_mod.evaluate_tool_call = original  # type: ignore[assignment]

    verdict = exc_info.value.verdict
    assert verdict.verdict is VerdictLabel.BLOCK
    rule_names = [r.rule for r in verdict.rules]
    assert "defenseclaw_backend_unavailable" in rule_names
    assert len(verdict.rules) == 1


# ---------------------------------------------------------------------------
# B3. _rewrite_request rejects empty sanitized_args for non-empty input.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewrite_request_rejects_empty_sanitized_args() -> None:
    """MODIFY with sanitized_args={} on non-empty input is a contract violation."""

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.MODIFY,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")],
            surface="mw_tool",
            latency_ms=0.0,
            modifications={"sanitized_args": {}},
        )

    mw = SafetyToolMiddleware()
    _, handler = _record_handler()
    request = _make_request("store_note", {"text": "user data"})
    original = tool_mw_mod.judge_tool_call
    tool_mw_mod.judge_tool_call = fake_judge  # type: ignore[assignment]
    try:
        with pytest.raises(SplunkGateError) as exc_info:
            await mw.tool_middleware(request, handler)
    finally:
        tool_mw_mod.judge_tool_call = original  # type: ignore[assignment]
    assert "empty sanitized_args" in str(exc_info.value)


# ---------------------------------------------------------------------------
# I4. AI Defense unmapped rule (Code Detection) forces BLOCK (PR-117 shape).
# ---------------------------------------------------------------------------


class _FixedAIDefense:
    """Returns a fixed InspectResponse regardless of input."""

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


def _code_detection_high_response() -> _InspectResponse:
    """AI Defense returns a rule with NO v1 redactor (Code Detection)."""
    return _InspectResponse(
        is_safe=False,
        severity=Severity.MEDIUM,
        rules=[
            _AIDefRuleHit(
                rule_name=AIDefenseRule.CODE_DETECTION,
                classification=Classification.SECURITY_VIOLATION,
            ),
        ],
        explanation="code detection hit",
    )


@pytest.mark.asyncio
async def test_compose_sanitized_unmapped_rule_forces_block() -> None:
    """AI Defense returning Code Detection (no v1 redactor) MUST force BLOCK.

    Per PR #117 silent-failure shape: a missing redactor entry would
    otherwise produce byte-identical sanitized_args under MODIFY, and the
    dangerous payload would reach the downstream tool. Force BLOCK + WARN.
    """
    assert not is_supported_rule("Code Detection")  # sanity: it really is unmapped
    fake = _FixedAIDefense(_code_detection_high_response())
    cfg = Config(escalate_on_first_pass_hit=True)
    mw = SafetyToolMiddleware(
        config=cfg,
        ai_defense=cast("AIDefenseLike", fake),
    )
    _, handler = _record_handler()
    request = _make_request("store_note", {"text": "user ssn is 123-45-6789"})

    with pytest.raises(ToolBlockedBySplunkGate) as exc_info:
        await mw.tool_middleware(request, handler)

    assert fake.call_count == 1
    verdict = exc_info.value.verdict
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.modifications is None
    rule_names = [r.rule for r in verdict.rules]
    assert "PII" in rule_names
    assert "Code Detection" in rule_names


# ---------------------------------------------------------------------------
# End-to-end: MODIFY through real DefenseClaw cheap path preserves keys.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modify_via_real_defenseclaw_path_preserves_keys_redacts_pii() -> None:
    """End-to-end MODIFY through real DefenseClaw cheap-pass: keys preserved + PII redacted."""
    mw = SafetyToolMiddleware()
    seen, handler = _record_handler()
    original_args = {"query": "user SSN is 123-45-6789, name=Alice"}
    request = _make_request("store_note", original_args)
    original_args_copy = dict(request.call.args)

    response = await mw.tool_middleware(request, handler)

    assert response is not None
    assert len(seen) == 1
    sanitized = seen[0].call.args
    assert set(sanitized.keys()) == set(original_args.keys())
    assert "[REDACTED:PII]" in sanitized["query"]  # type: ignore[operator]
    assert "123-45-6789" not in sanitized["query"]  # type: ignore[operator]
    assert request.call.args == original_args_copy


# ---------------------------------------------------------------------------
# AI Defense is_safe=True keeps cheap-pass BLOCK (Shell Injection branch).
# ---------------------------------------------------------------------------


def _safe_ai_defense_response() -> _InspectResponse:
    return _InspectResponse(
        is_safe=True,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation="clean",
    )


@pytest.mark.asyncio
async def test_ai_defense_is_safe_true_keeps_cheap_block() -> None:
    """Cheap Shell Injection hit + AI Defense is_safe=True → cheap branch still wins."""
    fake = _FixedAIDefense(_safe_ai_defense_response())
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
    verdict = exc_info.value.verdict
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.severity is Severity.HIGH
    assert any(r.source == "defenseclaw_regex" for r in verdict.rules)
    assert not any(r.source == "ai_defense" for r in verdict.rules)


# ---------------------------------------------------------------------------
# Deeply nested args: cheap PII hit + MODIFY redacts nested string.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deeply_nested_args_detected_no_padding_bypass() -> None:
    """Cheap pass detects PII inside nested dicts; MODIFY redacts the nested leaf."""
    mw = SafetyToolMiddleware()
    seen, handler = _record_handler()
    request = _make_request(
        "store_note",
        {"outer": {"inner": {"deeper": "ssn 123-45-6789"}}},
    )

    await mw.tool_middleware(request, handler)

    assert len(seen) == 1
    sanitized = seen[0].call.args
    outer = sanitized["outer"]
    assert isinstance(outer, dict)
    inner = outer["inner"]
    assert isinstance(inner, dict)
    deeper = inner["deeper"]
    assert isinstance(deeper, str)
    assert "[REDACTED:PII]" in deeper
    assert "123-45-6789" not in deeper

"""Regression tests for PR #128 review findings on SafetySubagentMiddleware.

Lives in its own file so the main behavioral test file stays under the
400-LOC cap. Each test locks one specific review finding:
- test_review_label_falls_closed_to_block — Critical #2 (REVIEW silent ALLOW)
- test_fail_closed_verdict_carries_subagent_surface — Critical #1 (wrong surface)
- test_unsupported_args_type_fails_closed — Important #5 (raw TypeError on list)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
import splunkgate_mw.subagent_middleware as subagent_mw_mod
from splunkgate_core.errors import SubagentBlockedBySplunkGate
from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from splunkgate_mw.subagent_middleware import SafetySubagentMiddleware
from splunklib.ai.messages import HumanMessage, SubagentCall, SubagentTextResult
from splunklib.ai.middleware import AgentState, SubagentRequest, SubagentResponse

_Handler = Callable[[SubagentRequest], Awaitable[SubagentResponse]]


def _make_request(
    name: str = "summarizer",
    args: dict[str, object] | str | None = None,
) -> SubagentRequest:
    call_args: str | dict[str, object] = (
        {"input": "summarize this document"} if args is None else args
    )
    call = SubagentCall(id="sub-call-1", name=name, args=call_args, thread_id="thread-1")
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content="ok")]),
        thread_id="thread-1",
    )
    return SubagentRequest(call=call, state=state)


def _record_handler() -> tuple[list[SubagentRequest], _Handler]:
    seen: list[SubagentRequest] = []

    async def handler(request: SubagentRequest) -> SubagentResponse:
        seen.append(request)
        return SubagentResponse(result=SubagentTextResult(content="summary"))

    return seen, handler


@pytest.mark.asyncio
async def test_review_label_falls_closed_to_block() -> None:
    """VerdictLabel.REVIEW (and any future label) must NOT silently ALLOW."""

    async def fake_judge(*_args: object, **_kwargs: object) -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.REVIEW,
            severity=Severity.MEDIUM,
            rules=[RuleHit(rule="Prompt Injection", confidence=0.5, source="ai_defense")],
            surface="mw_subagent",
            latency_ms=0.0,
        )

    mw = SafetySubagentMiddleware()
    seen, handler = _record_handler()
    request = _make_request("summarizer", {"input": "review me"})
    original = subagent_mw_mod.judge_subagent_call
    subagent_mw_mod.judge_subagent_call = fake_judge  # type: ignore[assignment]
    try:
        with pytest.raises(SubagentBlockedBySplunkGate):
            await mw.subagent_middleware(request, handler)
    finally:
        subagent_mw_mod.judge_subagent_call = original  # type: ignore[assignment]
    assert len(seen) == 0


@pytest.mark.asyncio
async def test_fail_closed_verdict_carries_subagent_surface() -> None:
    """When the cheap pass crashes, the synthetic BLOCK verdict has surface='mw_subagent'."""
    import splunkgate_mw._fail_closed as fc_mod  # noqa: PLC0415

    msg = "synthetic defenseclaw failure"

    async def raising_evaluate(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(msg)

    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    request = _make_request("summarizer", {"input": "anything"})
    # Patch the name `_fail_closed.evaluate_tool_call` since that's the
    # binding `run_cheap_pass` resolves at call time. Patching the
    # original module won't take effect because the import is already
    # bound in `_fail_closed.py`.
    original = fc_mod.evaluate_tool_call
    fc_mod.evaluate_tool_call = raising_evaluate  # type: ignore[assignment]
    try:
        with pytest.raises(SubagentBlockedBySplunkGate) as exc_info:
            await mw.subagent_middleware(request, handler)
    finally:
        fc_mod.evaluate_tool_call = original  # type: ignore[assignment]
    assert exc_info.value.verdict.surface == "mw_subagent"


@pytest.mark.asyncio
async def test_unsupported_args_type_fails_closed() -> None:
    """SubagentCall.args of an unsupported type (list, etc.) → fail-closed BLOCK."""
    mw = SafetySubagentMiddleware()
    _seen, handler = _record_handler()
    # Pass a list to bypass the type system; SubagentCall.args is typed
    # str | dict but at runtime nothing stops a future variant.
    request = _make_request("summarizer", cast("dict[str, object]", [("a", 1)]))
    with pytest.raises(SubagentBlockedBySplunkGate) as exc_info:
        await mw.subagent_middleware(request, handler)
    assert exc_info.value.verdict.surface == "mw_subagent"
    assert "subagent_args_unsupported_shape" in [r.rule for r in exc_info.value.verdict.rules]

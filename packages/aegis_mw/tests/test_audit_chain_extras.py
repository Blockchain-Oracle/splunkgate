"""Behavioral tests for the multi-verdict audit-chain extras (story-mw-08 / F1).

Closes GitHub issue #94. Verifies that `SafetyModelMiddleware` threads
`aegis_pre_trace_id` and `aegis_post_trace_id` into the returned
`AIMessage.extras` whenever the corresponding verdict was non-ALLOW.
The Regulator Evidence Pack dashboard (story-app-07) reads the chain
from this field in-band rather than joining OTel events post-hoc.
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from aegis_core.verdict import RuleHit, Severity, Verdict, VerdictLabel
from aegis_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    InspectRequest,
    InspectResponse,
)
from aegis_judges.ai_defense_types import RuleHit as InspectRuleHit
from aegis_mw import model_middleware as mw_mod
from aegis_mw.model_middleware import (
    SafetyModelMiddleware,
    _build_audit_extras,
    _with_extras,
)
from splunklib.ai.messages import AIMessage, HumanMessage
from splunklib.ai.middleware import AgentState, ModelRequest, ModelResponse

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _verdict(
    label: VerdictLabel,
    severity: Severity = Severity.MEDIUM,
    *,
    surface: str = "mw_model",
) -> Verdict:
    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=severity,
        rules=[RuleHit(rule="PII", confidence=1.0, source="ai_defense")],
        modifications={"redacted_text": "[REDACTED]"} if label is VerdictLabel.MODIFY else None,
        surface=cast("str", surface),
        latency_ms=1.0,
    )


def _request(content: str = "hello") -> ModelRequest:
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content=content)]),
        thread_id="test-thread",
    )
    return ModelRequest(system_message="be helpful", state=state)


class _MediumPIIClient:
    """AIDefenseLike stub that always returns MEDIUM PII → MODIFY semantics."""

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        _ = request, trace_id
        return InspectResponse(
            is_safe=False,
            severity=Severity.MEDIUM,
            rules=[
                InspectRuleHit(
                    rule_name=AIDefenseRule.PII,
                    classification=Classification.PRIVACY_VIOLATION,
                )
            ],
        )


class _BenignClient:
    """AIDefenseLike stub that always returns ALLOW (is_safe=True)."""

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        _ = request, trace_id
        return InspectResponse(is_safe=True, severity=Severity.NONE_SEVERITY)


# ─── Pure-function unit tests ────────────────────────────────────────────────


def test_build_audit_extras_returns_none_when_both_allow() -> None:
    """ALLOW pre + ALLOW post → no audit annotation needed."""
    pre = _verdict(VerdictLabel.ALLOW)
    post = _verdict(VerdictLabel.ALLOW)
    assert _build_audit_extras(pre, post) is None


def test_build_audit_extras_returns_none_when_no_pre_and_post_allow() -> None:
    """ALLOW pre (None=skipped) + ALLOW post → no audit annotation needed."""
    post = _verdict(VerdictLabel.ALLOW)
    assert _build_audit_extras(None, post) is None


def test_build_audit_extras_post_modify_only() -> None:
    """ALLOW pre + MODIFY post → only post trace_id surfaces."""
    pre = _verdict(VerdictLabel.ALLOW)
    post = _verdict(VerdictLabel.MODIFY)
    out = _build_audit_extras(pre, post)
    assert out == {"aegis_post_trace_id": str(post.trace_id)}


def test_build_audit_extras_pre_modify_post_allow() -> None:
    """MODIFY pre + ALLOW post → only pre trace_id surfaces."""
    pre = _verdict(VerdictLabel.MODIFY)
    post = _verdict(VerdictLabel.ALLOW)
    out = _build_audit_extras(pre, post)
    assert out == {"aegis_pre_trace_id": str(pre.trace_id)}


def test_build_audit_extras_pre_and_post_both_modify() -> None:
    """MODIFY pre + MODIFY post → both trace_ids surface."""
    pre = _verdict(VerdictLabel.MODIFY)
    post = _verdict(VerdictLabel.MODIFY)
    out = _build_audit_extras(pre, post)
    assert out == {
        "aegis_pre_trace_id": str(pre.trace_id),
        "aegis_post_trace_id": str(post.trace_id),
    }


def test_with_extras_preserves_upstream_message_extras() -> None:
    """Upstream agent extras coexist with aegis_* keys; aegis wins on collision."""
    msg = AIMessage(
        content="hello",
        calls=[],
        extras={"foo": "bar", "aegis_pre_trace_id": "STALE"},
    )
    new = _with_extras(msg, {"aegis_pre_trace_id": "NEW", "aegis_post_trace_id": "POST"})
    assert new.content == "hello"
    assert new.extras == {
        "foo": "bar",
        "aegis_pre_trace_id": "NEW",
        "aegis_post_trace_id": "POST",
    }


def test_with_extras_handles_none_existing_extras() -> None:
    """AIMessage.extras=None coerces to an empty dict before merging."""
    msg = AIMessage(content="hi", calls=[], extras=None)
    new = _with_extras(msg, {"aegis_post_trace_id": "abc"})
    assert new.extras == {"aegis_post_trace_id": "abc"}


def test_aegis_pre_trace_id_value_is_uuid_string() -> None:
    """Trace id values are stringified UUIDs (auditor-friendly form)."""
    pre = _verdict(VerdictLabel.MODIFY)
    out = _build_audit_extras(pre, _verdict(VerdictLabel.ALLOW))
    assert out is not None
    UUID(str(out["aegis_pre_trace_id"]))  # raises on malformed uuid


# ─── Integration tests via monkey-patched pre_inference_scan ─────────────────


_Handler = Callable[[ModelRequest], Awaitable[ModelResponse]]


def _allow_handler_returning(content: str) -> _Handler:
    async def handler(_req: ModelRequest) -> ModelResponse:
        return ModelResponse(message=AIMessage(content=content, calls=[]))

    return handler


@pytest.mark.asyncio
async def test_pre_modify_post_allow_threads_pre_trace_id_to_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When pre-MODIFY fires + post-scan is ALLOW, the original-shape response
    carries the pre verdict's trace_id in extras for auditor recovery.
    """
    pre_v = _verdict(VerdictLabel.MODIFY)

    async def _fake_pre(*_args: object, **_kwargs: object) -> Verdict:
        return pre_v

    monkeypatch.setattr(mw_mod, "pre_inference_scan", _fake_pre)

    mw = SafetyModelMiddleware(ai_defense=_BenignClient())
    result = await mw.model_middleware(_request(), _allow_handler_returning("benign output"))

    assert result.message.extras == {"aegis_pre_trace_id": str(pre_v.trace_id)}
    assert result.message.content == "benign output"


@pytest.mark.asyncio
async def test_pre_modify_post_modify_threads_both_trace_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both pre and post fire MODIFY, both trace_ids surface in extras."""
    pre_v = _verdict(VerdictLabel.MODIFY)

    async def _fake_pre(*_args: object, **_kwargs: object) -> Verdict:
        return pre_v

    monkeypatch.setattr(mw_mod, "pre_inference_scan", _fake_pre)

    mw = SafetyModelMiddleware(ai_defense=_MediumPIIClient())
    result = await mw.model_middleware(
        _request(), _allow_handler_returning("model said something PII-ish")
    )

    assert result.message.content == "[REDACTED]"
    extras = result.message.extras or {}
    assert extras["aegis_pre_trace_id"] == str(pre_v.trace_id)
    assert "aegis_post_trace_id" in extras
    UUID(str(extras["aegis_post_trace_id"]))


@pytest.mark.asyncio
async def test_pre_allow_post_modify_threads_post_trace_id_only() -> None:
    """ALLOW pre + MODIFY post → only post trace_id surfaces (no pre)."""
    mw = SafetyModelMiddleware(ai_defense=_MediumPIIClient())
    result = await mw.model_middleware(_request(), _allow_handler_returning("model said PII"))
    assert result.message.content == "[REDACTED]"
    extras = result.message.extras or {}
    assert "aegis_pre_trace_id" not in extras
    assert "aegis_post_trace_id" in extras


@pytest.mark.asyncio
async def test_pre_allow_post_allow_returns_original_response_unchanged() -> None:
    """ALLOW + ALLOW → original ModelResponse returned by identity, no extras added."""
    original = ModelResponse(message=AIMessage(content="benign", calls=[]))

    async def handler(_req: ModelRequest) -> ModelResponse:
        return original

    mw = SafetyModelMiddleware(ai_defense=_BenignClient())
    result = await mw.model_middleware(_request(), handler)
    assert result is original
    assert result.message.extras is None

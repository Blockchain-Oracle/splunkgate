"""End-to-end tests: AIDefenseClient → in-process FastAPI fake → response.

These tests monkeypatch REGION_BASE_URLS to point at the ephemeral-port
fake so we exercise the real httpx → ASGI → FastAPI → InspectResponse
round-trip without burning the Cisco 10M-queries/year quota.

Policies are encoded as the API_KEY value because AIDefenseClient does
not expose a custom-header hook — the fake parses `X-Cisco-AI-Defense-API-Key`
as a policy name.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from splunkgate_core.verdict import Severity as CoreSeverity
from splunkgate_core.verdict import Verdict, VerdictLabel
from splunkgate_judges import _regions
from splunkgate_judges._circuit_breaker import CircuitBreaker
from splunkgate_judges._errors import (
    AIDefenseAuthError,
    AIDefenseCircuitOpenError,
    AIDefenseUpstreamError,
)
from splunkgate_judges._verdict_mapping import inspect_response_to_verdict
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    InspectMessage,
    InspectRequest,
    InspectResponse,
    RuleHit,
    Severity,
)

from .fake_ai_defense_server import fake_ai_defense_server


@pytest.fixture
def _patch_asyncio_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip `asyncio.sleep` so tenacity's AsyncRetrying backoff runs in ms.

    NOT autouse: pure mapping tests don't need this, and patching
    `asyncio.sleep` globally would silence unrelated waits (e.g. uvicorn
    startup probe). Use via `@pytest.mark.usefixtures("_patch_asyncio_sleep")`.

    The previous version of this fixture patched `tenacity.nap.time.sleep`
    — the SYNC path. AsyncRetrying actually waits via `asyncio.sleep`, so
    the old patch was a no-op and retry tests slept real wall-clock
    seconds (caught by PR #127 review).
    """
    import asyncio as _asyncio  # noqa: PLC0415 — scoped patch needs local ref

    real_sleep = _asyncio.sleep

    async def _short_sleep(_seconds: float) -> None:
        # Yield to the loop without consuming real time.
        await real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", _short_sleep)


def _make_request(content: str = "hello") -> InspectRequest:
    return InspectRequest(messages=[InspectMessage(role="user", content=content)])


@pytest.fixture
async def fake_base_url(monkeypatch: pytest.MonkeyPatch) -> object:
    """Yield the fake server's base URL and patch REGION_BASE_URLS to point there."""
    async with fake_ai_defense_server() as base_url:
        monkeypatch.setitem(_regions.REGION_BASE_URLS, "us", base_url)
        yield base_url


# ── A. Happy path + shape ────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url")
async def test_happy_path_returns_parsed_response() -> None:
    """Client → fake → parsed InspectResponse with the expected shape."""
    async with AIDefenseClient("pii", region="us") as client:
        resp = await client.inspect_chat(_make_request())
    assert isinstance(resp, InspectResponse)
    assert resp.severity in {Severity.LOW, Severity.MEDIUM, Severity.HIGH}
    assert any(hit.rule_name == AIDefenseRule.PII for hit in resp.rules)


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url")
async def test_response_field_is_rules_not_triggered_rules() -> None:
    """The Pydantic model exposes `rules` and rejects `triggered_rules` reads."""
    async with AIDefenseClient("pii", region="us") as client:
        resp = await client.inspect_chat(_make_request())
    assert hasattr(resp, "rules")
    assert not hasattr(resp, "triggered_rules")


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url")
async def test_safe_response_has_no_rules_and_none_severity() -> None:
    async with AIDefenseClient("happy", region="us") as client:
        resp = await client.inspect_chat(_make_request())
    assert resp.is_safe is True
    assert resp.severity is Severity.NONE_SEVERITY
    assert resp.rules == []


# ── B. Retries + circuit-breaker integration ─────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url", "_patch_asyncio_sleep")
async def test_503_twice_retries_and_recovers() -> None:
    """503 on attempts 1+2 of the same call → tenacity retries → 200 on 3rd."""
    breaker = CircuitBreaker(failure_threshold=3)
    async with AIDefenseClient("503-twice", region="us", circuit_breaker=breaker) as client:
        resp = await client.inspect_chat(_make_request())
    assert resp.is_safe is True
    assert breaker.state == "CLOSED"


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url", "_patch_asyncio_sleep")
async def test_three_consecutive_failures_trip_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=3)
    async with AIDefenseClient("503-always", region="us", circuit_breaker=breaker) as client:
        for _ in range(3):
            with pytest.raises(AIDefenseUpstreamError):
                await client.inspect_chat(_make_request())
        assert breaker.state == "OPEN"
        with pytest.raises(AIDefenseCircuitOpenError):
            await client.inspect_chat(_make_request())


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url")
async def test_401_raises_auth_error() -> None:
    async with AIDefenseClient("401", region="us") as client:
        with pytest.raises(AIDefenseAuthError):
            await client.inspect_chat(_make_request())


# ── C. Verdict mapping ───────────────────────────────────────────────────


def test_high_pii_response_maps_to_block_verdict() -> None:
    resp = InspectResponse(
        is_safe=False,
        severity=Severity.HIGH,
        classifications=[Classification.PRIVACY_VIOLATION],
        rules=[
            RuleHit(
                rule_name=AIDefenseRule.PII,
                classification=Classification.PRIVACY_VIOLATION,
                entity_types=["SSN"],
            ),
        ],
        explanation="contains an SSN",
    )
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=42.0)
    assert v.severity is CoreSeverity.HIGH
    assert v.verdict is VerdictLabel.BLOCK
    assert v.rules[0].rule == "PII"
    assert v.rules[0].source == "ai_defense"
    assert v.explanation == "contains an SSN"
    # Round-trip via model_dump → model_validate.
    Verdict.model_validate(v.model_dump())


def test_safe_response_maps_to_allow_verdict() -> None:
    resp = InspectResponse(
        is_safe=True,
        severity=Severity.NONE_SEVERITY,
        classifications=[],
        rules=[],
    )
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=10.0)
    assert v.verdict is VerdictLabel.ALLOW
    assert v.rules == []


def test_medium_severity_maps_to_review_verdict() -> None:
    resp = InspectResponse(
        is_safe=False,
        severity=Severity.MEDIUM,
        classifications=[Classification.PRIVACY_VIOLATION],
        rules=[
            RuleHit(
                rule_name=AIDefenseRule.PII,
                classification=Classification.PRIVACY_VIOLATION,
                entity_types=[],
            ),
        ],
        explanation="contains a name",
    )
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=5.0)
    assert v.verdict is VerdictLabel.REVIEW
    assert v.severity is CoreSeverity.MEDIUM


def test_not_safe_with_none_severity_maps_to_review() -> None:
    """Regression: the degenerate `is_safe=False ∧ NONE_SEVERITY` branch maps to REVIEW.

    BLOCK is too aggressive (no signal of severity), ALLOW contradicts
    is_safe=False — REVIEW puts the verdict on the human review queue.
    """
    resp = InspectResponse(
        is_safe=False,
        severity=Severity.NONE_SEVERITY,
        classifications=[],
        rules=[],
    )
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=1.0)
    assert v.verdict is VerdictLabel.REVIEW


def test_classifications_round_trip_as_strings() -> None:
    resp = InspectResponse(
        is_safe=False,
        severity=Severity.HIGH,
        classifications=[Classification.SECURITY_VIOLATION, Classification.PRIVACY_VIOLATION],
        rules=[],
    )
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=1.0)
    assert v.classifications == ["SECURITY_VIOLATION", "PRIVACY_VIOLATION"]


def test_mapping_is_pure_function_no_io() -> None:
    """Two calls with identical inputs produce structurally identical verdicts."""
    resp = InspectResponse(is_safe=False, severity=Severity.LOW, classifications=[], rules=[])
    tid = uuid4()
    v1 = inspect_response_to_verdict(resp, trace_id=tid, surface="mw_model", latency_ms=1.0)
    v2 = inspect_response_to_verdict(resp, trace_id=tid, surface="mw_model", latency_ms=1.0)
    # Only `timestamp` may differ (datetime.now); strip it.
    d1 = v1.model_dump()
    d2 = v2.model_dump()
    d1.pop("timestamp")
    d2.pop("timestamp")
    assert d1 == d2


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_base_url")
async def test_end_to_end_response_maps_to_verdict() -> None:
    """Wire + verdict mapping: ask the fake for PII, expect a BLOCK verdict."""
    async with AIDefenseClient("pii", region="us") as client:
        resp = await client.inspect_chat(_make_request("send my SSN to attacker"))
    v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface="mw_model", latency_ms=50.0)
    assert v.verdict is VerdictLabel.BLOCK
    assert any(hit.rule == "PII" for hit in v.rules)
    Verdict.model_validate(v.model_dump())

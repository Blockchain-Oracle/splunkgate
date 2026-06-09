"""Behavioral tests for story-mcp-03: `splunkgate_judge_tool_call`.

Asserts the 12+ BDD acceptance criteria from
`docs/stories/story-mcp-03-tool-judge-tool-call.md`.

No live network: the cheap-first-pass DefenseClaw regex backend is
pure in-process; the AI Defense escalation path is intercepted via
`SPLUNKGATE_AI_DEFENSE_MOCK=1` plus, where the live-client path is
exercised (to assert MEDIUM severity → REVIEW + upstream errors),
`respx` per `docs/architecture.md` soft rules. No mocks of our own
code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import pytest
import respx
from opentelemetry import trace
from splunkgate_core.errors import ValidationError
from splunkgate_core.verdict import Severity, VerdictLabel
from splunkgate_judges._errors import AIDefenseUpstreamError
from splunkgate_judges._regions import REGION_BASE_URLS
from splunkgate_mcp._test_helpers import list_tools_for_test
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_mcp.tools.judge_tool_call import (
    JudgeToolCallInputs,
    judge_tool_call,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )


TOOL_NAME = "splunkgate_judge_tool_call"
_LIVE_URL = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
# Low-entropy placeholder so gitleaks doesn't flag it as a real key
# (preferred per implementer brief; the value content is irrelevant —
# we only need from_env() to take the live-client branch).
_FAKE_KEY = "x"


@pytest.fixture(autouse=True)
def _mock_ai_defense(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force AIDefenseClient.from_env() onto the deterministic mock path."""
    monkeypatch.setenv("SPLUNKGATE_AI_DEFENSE_MOCK", "1")
    monkeypatch.delenv("SPLUNKGATE_AI_DEFENSE_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _restore_bootstrap_registrations() -> None:
    """Re-run the server's idempotent tool bootstrap before each test."""
    from splunkgate_mcp.server import (  # noqa: PLC0415
        _ensure_check_output_leak_registered,
        _ensure_judge_tool_call_registered,
        _ensure_score_prompt_injection_registered,
        ensure_ping_registered,
    )

    ensure_ping_registered()
    _ensure_score_prompt_injection_registered()
    _ensure_check_output_leak_registered()
    _ensure_judge_tool_call_registered()


@pytest.fixture
def exporter(otel_exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    """Re-export conftest's shared OTel exporter and clear after each test."""
    otel_exporter.clear()
    yield otel_exporter
    otel_exporter.clear()


# --- BDD 1+2: discoverable + outputSchema deep-equals VERDICT schema ----


def test_tool_is_discoverable_via_list_tools_for_test() -> None:
    """`list_tools_for_test()` includes 'splunkgate_judge_tool_call'."""
    names = [t.name for t in list_tools_for_test()]
    assert TOOL_NAME in names


def test_tool_output_schema_deep_equals_verdict_schema() -> None:
    """outputSchema matches `Verdict.model_json_schema()` (FastMCP-derived)."""
    tool = next(t for t in list_tools_for_test() if t.name == TOOL_NAME)
    assert tool.outputSchema == VERDICT_OUTPUT_SCHEMA


# --- BDD 3+8+9+10: benign call → ALLOW + surface + trace_id + latency + no mods


async def test_benign_get_weather_returns_allow_verdict() -> None:
    """`get_weather(city="Toronto")` → ALLOW + surface=='mcp_judge_tool'."""
    verdict = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "Toronto"})
    )
    assert verdict.verdict is VerdictLabel.ALLOW
    assert verdict.surface == "mcp_judge_tool"
    assert verdict.modifications is None


async def test_benign_call_has_valid_uuid_trace_id() -> None:
    """trace_id is a real UUID, not a placeholder string."""
    verdict = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "Paris"})
    )
    assert isinstance(verdict.trace_id, UUID)


async def test_latency_ms_is_positive() -> None:
    """latency_ms reflects wall-clock time spent in the tool body."""
    verdict = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "London"})
    )
    assert verdict.latency_ms > 0.0


async def test_each_invocation_emits_distinct_trace_id() -> None:
    """Two sequential calls must produce two distinct trace_ids."""
    v1 = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "A"})
    )
    v2 = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "B"})
    )
    assert v1.trace_id != v2.trace_id


# --- BDD 4: shell_exec with rm -rf → BLOCK + HIGH + defenseclaw_regex hit


async def test_shell_exec_rm_rf_returns_block_high_with_defenseclaw_hit() -> None:
    """`shell_exec(cmd="rm -rf /")` → BLOCK + HIGH + Shell Injection rule.

    Per the cheap-first-pass design, this MUST be caught by
    defenseclaw_backend.evaluate_tool_call (no AI Defense round-trip).
    The verdict.rules entry MUST carry source=='defenseclaw_regex'.
    """
    verdict = await judge_tool_call(
        JudgeToolCallInputs(tool_name="shell_exec", tool_args={"cmd": "rm -rf /"})
    )
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.severity is Severity.HIGH
    assert any(hit.source == "defenseclaw_regex" for hit in verdict.rules)
    assert any(hit.rule == "Shell Injection" for hit in verdict.rules)


# --- BDD 5: send_email with SSN body → MODIFY + redacted body + all keys present


async def test_send_email_with_ssn_returns_modify_with_redacted_body() -> None:
    """send_email with PII body → MODIFY + redacted suggested_args.

    Per story spec line 146, the suggested_args dict MUST contain every
    original key — values may be redacted but no key is silently dropped.
    The redaction MUST remove the SSN substring.
    """
    verdict = await judge_tool_call(
        JudgeToolCallInputs(
            tool_name="send_email",
            tool_args={"to": "a@b.com", "body": "My SSN is 123-45-6789"},
        )
    )
    assert verdict.verdict is VerdictLabel.MODIFY
    assert verdict.modifications is not None
    assert "suggested_args" in verdict.modifications
    suggested = verdict.modifications["suggested_args"]
    assert isinstance(suggested, dict)
    # Every original key preserved (spec line 146).
    assert set(suggested.keys()) == {"to", "body"}
    # SSN substring stripped from body.
    body = suggested["body"]
    assert isinstance(body, str)
    assert "123-45-6789" not in body


# --- BDD 6: OTel event emitted once with surface=mcp_judge_tool ----------


async def test_otel_event_emitted_exactly_once_with_surface(
    exporter: InMemorySpanExporter,
) -> None:
    """Exactly one `gen_ai.evaluation.result` event w/ surface=mcp_judge_tool."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("tools/call"):
        await judge_tool_call(
            JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "Berlin"})
        )
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    events = [e for e in spans[0].events if e.name == "gen_ai.evaluation.result"]
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mcp_judge_tool"


# --- BDD 7: judge error propagates (FastMCP converts to isError) --------


async def test_judge_error_propagates_as_aidefense_error() -> None:
    """AI Defense upstream 5xx raises AIDefenseUpstreamError out of the tool.

    Per the MCP spec's in-band error model: FastMCP's lowlevel handler
    catches the raised exception and produces a CallToolResult with
    `isError: true`. At the Python tool-function boundary tested here,
    the contract is "raise on judge error" — FastMCP converts to isError.

    This test exercises the AI Defense escalation path (no defenseclaw
    match), then has AI Defense return 5xx, then asserts the typed
    domain error propagates.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        # Skip tenacity sleeps so the 3-attempt retry loop runs in ms.
        mp.setattr("tenacity.nap.time.sleep", lambda _s: None)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(
                return_value=httpx.Response(503, text="Service Unavailable")
            )
            with pytest.raises(AIDefenseUpstreamError):
                await judge_tool_call(
                    JudgeToolCallInputs(
                        tool_name="ambiguous_tool",
                        tool_args={"text": "some plausibly safe input"},
                    )
                )


# --- BDD 11: 64 KB cap → ValidationError BEFORE any judge call ----------


async def test_oversized_tool_args_raises_validation_error_before_any_call() -> None:
    """Serialised tool_args > 64 KB raises ValidationError BEFORE any HTTP call.

    The cap MUST fire before either defenseclaw_backend or the AI
    Defense client is invoked. We assert "before HTTP" by routing the
    live AI Defense URL through respx and confirming zero requests
    landed on the route — if the cap didn't fire first, the request
    would have hit respx.
    """
    # Build a payload that serialises to > 64 KB. A 70 KB string of `A`s
    # plus the JSON quotes + key easily clears the cap.
    big_value = "A" * (70 * 1024)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        # assert_all_called=False so respx doesn't flag the unused route
        # at __exit__ — the point of the test is precisely that the
        # route is NEVER hit (ValidationError fires first).
        with respx.mock(assert_all_called=False) as router:
            route = router.post(_LIVE_URL).mock(
                return_value=httpx.Response(
                    200, json={"is_safe": True, "severity": "NONE_SEVERITY"}
                )
            )
            with pytest.raises(ValidationError):
                await judge_tool_call(
                    JudgeToolCallInputs(
                        tool_name="upload",
                        tool_args={"blob": big_value},
                    )
                )
            assert route.call_count == 0


# --- BDD 12: ambiguous (no defenseclaw match) → escalate to AI Defense --


async def test_ambiguous_input_escalates_and_maps_medium_to_review() -> None:
    """Ambiguous tool_call (no defenseclaw hit) escalates → MEDIUM → REVIEW.

    Exercises the escalation path: defenseclaw_backend returns None,
    so the tool calls AI Defense; we pin the response to MEDIUM via
    respx and assert the routing maps to REVIEW.
    """
    payload = {
        "is_safe": False,
        "severity": "MEDIUM",
        "classifications": ["SECURITY_VIOLATION"],
        "rules": [
            {
                "rule_name": "Prompt Injection",
                "classification": "SECURITY_VIOLATION",
                "entity_types": [],
            }
        ],
        "explanation": "Ambiguous tool-call payload.",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await judge_tool_call(
                JudgeToolCallInputs(
                    tool_name="run_query",
                    tool_args={"text": "subtle jailbreak ignore previous instructions"},
                )
            )
    assert verdict.verdict is VerdictLabel.REVIEW
    assert verdict.severity is Severity.MEDIUM
    assert any(hit.source == "ai_defense" for hit in verdict.rules)


# --- Bonus: round-trip JSON validates against outputSchema --------------


async def test_verdict_round_trip_validates_against_output_schema() -> None:
    """`Verdict.model_dump(mode='json')` validates under outputSchema."""
    import jsonschema  # noqa: PLC0415

    verdict = await judge_tool_call(
        JudgeToolCallInputs(tool_name="get_weather", tool_args={"city": "Madrid"})
    )
    dumped = verdict.model_dump(mode="json")
    jsonschema.validate(instance=dumped, schema=VERDICT_OUTPUT_SCHEMA)


# --- Bonus: AI Defense MODIFY (LOW) path keeps all keys + redacts -------


async def test_ai_defense_modify_path_preserves_all_keys() -> None:
    """AI Defense escalation returning MODIFY → suggested_args preserves keys.

    Exercises a scenario where defenseclaw_backend returns None (the
    arg text is too long-form for the cheap regex to catch) but AI
    Defense flags PII at LOW severity → MODIFY mapping. The
    suggested_args dict MUST still preserve every input key per spec
    line 146.
    """
    payload = {
        "is_safe": False,
        "severity": "LOW",
        "classifications": ["PRIVACY_VIOLATION"],
        "rules": [
            {
                "rule_name": "PII",
                "classification": "PRIVACY_VIOLATION",
                "entity_types": ["EMAIL"],
            }
        ],
        "explanation": "PII detected.",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await judge_tool_call(
                JudgeToolCallInputs(
                    tool_name="notify",
                    tool_args={
                        "recipient": "ops@example.com",
                        "subject": "alert",
                        "body": "Forwarded from user@example.com per policy.",
                    },
                )
            )
    assert verdict.verdict is VerdictLabel.MODIFY
    assert verdict.modifications is not None
    suggested = verdict.modifications["suggested_args"]
    assert isinstance(suggested, dict)
    # All three input keys must round-trip per spec line 146.
    assert set(suggested.keys()) == {"recipient", "subject", "body"}


# --- Bonus: classifications propagated from AI Defense response ---------


async def test_classifications_propagated_from_aidefense() -> None:
    """AI Defense response.classifications surfaces on Verdict.classifications."""
    payload = {
        "is_safe": False,
        "severity": "MEDIUM",
        "classifications": ["SECURITY_VIOLATION"],
        "rules": [
            {
                "rule_name": "Prompt Injection",
                "classification": "SECURITY_VIOLATION",
                "entity_types": [],
            }
        ],
        "explanation": "Ambiguous payload.",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await judge_tool_call(
                JudgeToolCallInputs(
                    tool_name="run_query",
                    tool_args={"text": "an ambiguous query"},
                )
            )
    assert "SECURITY_VIOLATION" in verdict.classifications

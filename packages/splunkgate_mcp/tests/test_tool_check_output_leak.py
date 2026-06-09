"""Behavioral tests for story-mcp-04: `splunkgate_check_output_leak`.

Asserts the 12 BDD acceptance criteria from
`docs/stories/story-mcp-04-tool-check-output-leak.md`.

No live network: outbound AI Defense traffic intercepted via the
`SPLUNKGATE_AI_DEFENSE_MOCK=1` env var (which `AIDefenseClient.from_env`
honours) plus, where the live-client path is exercised (to assert
request-body shape, MEDIUM-severity mapping, and upstream error
propagation), `respx` per `docs/architecture.md` soft rules. No mocks
of our own code.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import pytest
import respx
from opentelemetry import trace
from splunkgate_core.verdict import VerdictLabel
from splunkgate_judges._errors import AIDefenseUpstreamError
from splunkgate_judges._regions import REGION_BASE_URLS
from splunkgate_mcp._test_helpers import list_tools_for_test
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_mcp.tools.check_output_leak import (
    CheckOutputLeakInputs,
    check_output_leak,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )


TOOL_NAME = "splunkgate_check_output_leak"
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
    """Re-run the server's idempotent tool bootstrap before each test.

    `test_server_skeleton.py` clears `_REGISTERED_TOOLS` for isolation in
    some of its tests; calling the idempotent ensure_* helpers restores
    `_ping`, `splunkgate_score_prompt_injection`, AND our tool without
    spelunking private state.
    """
    from splunkgate_mcp.server import (  # noqa: PLC0415
        _ensure_check_output_leak_registered,
        _ensure_score_prompt_injection_registered,
        ensure_ping_registered,
    )

    ensure_ping_registered()
    _ensure_score_prompt_injection_registered()
    _ensure_check_output_leak_registered()


@pytest.fixture
def exporter(otel_exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    """Re-export conftest's shared OTel exporter and clear after each test."""
    otel_exporter.clear()
    yield otel_exporter
    otel_exporter.clear()


# --- BDD 1+2: discoverable + outputSchema deep-equals VERDICT schema ----


def test_tool_is_discoverable_via_list_tools_for_test() -> None:
    """`list_tools_for_test()` includes 'splunkgate_check_output_leak'."""
    names = [t.name for t in list_tools_for_test()]
    assert TOOL_NAME in names


def test_tool_output_schema_deep_equals_verdict_schema() -> None:
    """outputSchema matches `Verdict.model_json_schema()` (FastMCP-derived)."""
    tool = next(t for t in list_tools_for_test() if t.name == TOOL_NAME)
    assert tool.outputSchema == VERDICT_OUTPUT_SCHEMA


# --- BDD 3+9+10: benign output → ALLOW + surface + latency + trace_id ---


async def test_benign_output_returns_allow_verdict() -> None:
    """Benign weather output + sensitivity='default' → ALLOW + surface."""
    verdict = await check_output_leak(
        CheckOutputLeakInputs(
            output_text="The weather in Toronto today is sunny, 22C.",
            sensitivity="default",
        )
    )
    assert verdict.verdict is VerdictLabel.ALLOW
    assert verdict.surface == "mcp_check_output"


async def test_benign_output_has_valid_uuid_trace_id() -> None:
    """trace_id is a real UUID, not a placeholder string."""
    verdict = await check_output_leak(CheckOutputLeakInputs(output_text="Just a friendly hello."))
    assert isinstance(verdict.trace_id, UUID)


async def test_latency_ms_is_positive() -> None:
    """latency_ms reflects wall-clock time spent in the tool body."""
    verdict = await check_output_leak(CheckOutputLeakInputs(output_text="Have a nice day!"))
    assert verdict.latency_ms > 0.0


# --- BDD 4: SSN output → MODIFY + redacted_output -----------------------


async def test_ssn_output_returns_modify_with_redacted_pii_token() -> None:
    """'my ssn is 123-45-6789' triggers PII HIGH in the mock matrix.

    Per the routing rule in story spec line 152:
    - is_safe=False + HIGH on catastrophic rule (PII) → BLOCK
    - is_safe=False + non-HIGH → MODIFY (preserves agent utility)

    Our spec-matrix substring fixture lands on HIGH because the mock
    picks the highest-severity tier. Per the BDD case (line 46-50) the
    SSN case is tested at MODIFY though — so we exercise the LOW
    mapping via respx in a sibling test, and here we just assert that
    the verdict is one of the leak labels and the redacted_output
    strips the SSN.
    """
    verdict = await check_output_leak(
        CheckOutputLeakInputs(
            output_text="Confirmed: my ssn is 123-45-6789 on file.",
            sensitivity="default",
        )
    )
    # Either BLOCK (HIGH on catastrophic rule) or MODIFY; in both cases
    # we MUST surface a redacted view so callers can see what we stripped.
    assert verdict.verdict in (VerdictLabel.MODIFY, VerdictLabel.BLOCK)
    redacted = (verdict.modifications or {}).get("redacted_output", "")
    assert isinstance(redacted, str)
    assert "123-45-6789" not in redacted
    assert "[REDACTED:PII]" in redacted


async def test_ssn_low_severity_path_returns_modify() -> None:
    """SSN with LOW severity via respx → MODIFY + redacted PII token.

    Asserts BDD lines 46-50 exactly: PII hit → MODIFY (not BLOCK)
    with `[REDACTED:PII]` in modifications.redacted_output and the
    original SSN substring removed. Uses respx so we can pin severity
    to LOW (the mock's substring-index always picks HIGH).
    """
    payload = {
        "is_safe": False,
        "severity": "LOW",
        "classifications": ["PRIVACY_VIOLATION"],
        "rules": [
            {
                "rule_name": "PII",
                "classification": "PRIVACY_VIOLATION",
                "entity_types": ["SSN"],
            }
        ],
        "explanation": "PII detected (SSN).",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await check_output_leak(
                CheckOutputLeakInputs(
                    output_text="The user's SSN is 123-45-6789.",
                    sensitivity="default",
                )
            )
    assert verdict.verdict is VerdictLabel.MODIFY
    redacted = (verdict.modifications or {}).get("redacted_output", "")
    assert isinstance(redacted, str)
    assert "123-45-6789" not in redacted
    assert "[REDACTED:PII]" in redacted


# --- BDD 5: PCI / fsi enables PCI in request --------------------------


async def test_pci_output_with_fsi_sensitivity() -> None:
    """16-digit card + fsi → AI Defense request includes PCI + MODIFY + redacted."""
    payload = {
        "is_safe": False,
        "severity": "LOW",
        "classifications": ["PRIVACY_VIOLATION"],
        "rules": [
            {
                "rule_name": "PCI",
                "classification": "PRIVACY_VIOLATION",
                "entity_types": ["CREDIT_CARD"],
            }
        ],
        "explanation": "PCI detected (card number).",
    }
    captured: dict[str, object] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            route = router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await check_output_leak(
                CheckOutputLeakInputs(
                    output_text="Customer card: 4242 4242 4242 4242 charged successfully.",
                    sensitivity="fsi",
                )
            )
            captured["body"] = route.calls.last.request.content
    body_bytes = captured["body"]
    assert isinstance(body_bytes, bytes)
    body = json.loads(body_bytes)
    rule_names = [r["rule_name"] for r in body["config"]["enabled_rules"]]
    assert "PCI" in rule_names
    assert "PII" in rule_names  # fsi profile = [PII, PCI]

    assert verdict.verdict is VerdictLabel.MODIFY
    redacted = (verdict.modifications or {}).get("redacted_output", "")
    assert isinstance(redacted, str)
    assert "[REDACTED:PCI]" in redacted


# --- BDD 6: PHI / hipaa enables PHI in request -------------------------


async def test_phi_output_with_hipaa_sensitivity() -> None:
    """DOB + diagnosis + hipaa → request includes PHI + MODIFY + redacted."""
    payload = {
        "is_safe": False,
        "severity": "LOW",
        "classifications": ["PRIVACY_VIOLATION"],
        "rules": [
            {
                "rule_name": "PHI",
                "classification": "PRIVACY_VIOLATION",
                "entity_types": ["MEDICAL_RECORD"],
            }
        ],
        "explanation": "PHI detected.",
    }
    captured: dict[str, object] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            route = router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            verdict = await check_output_leak(
                CheckOutputLeakInputs(
                    output_text="Patient DOB 1975-03-12 diagnosed with hypertension.",
                    sensitivity="hipaa",
                )
            )
            captured["body"] = route.calls.last.request.content
    body_bytes = captured["body"]
    assert isinstance(body_bytes, bytes)
    body = json.loads(body_bytes)
    rule_names = [r["rule_name"] for r in body["config"]["enabled_rules"]]
    assert "PHI" in rule_names
    assert "PII" in rule_names  # hipaa profile = [PII, PHI]

    assert verdict.verdict is VerdictLabel.MODIFY
    redacted = (verdict.modifications or {}).get("redacted_output", "")
    assert isinstance(redacted, str)
    assert "[REDACTED:PHI]" in redacted


# --- BDD 7: OTel event with surface ------------------------------------


async def test_otel_event_emitted_exactly_once_with_surface(
    exporter: InMemorySpanExporter,
) -> None:
    """Exactly one `gen_ai.evaluation.result` event w/ surface=mcp_check_output."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("tools/call"):
        await check_output_leak(CheckOutputLeakInputs(output_text="Hello from the agent."))
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    events = [e for e in spans[0].events if e.name == "gen_ai.evaluation.result"]
    assert len(events) == 1
    attrs = dict(events[0].attributes or {})
    assert attrs["splunkgate.surface"] == "mcp_check_output"


# --- BDD 8: judge error propagates -------------------------------------


async def test_judge_error_propagates_as_aidefense_error() -> None:
    """AI Defense upstream 5xx raises AIDefenseUpstreamError out of the tool."""
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
                await check_output_leak(
                    CheckOutputLeakInputs(
                        output_text="Some output text that triggers an upstream call.",
                        sensitivity="default",
                    )
                )


# --- BDD 11: trace_id uniqueness ---------------------------------------


async def test_each_invocation_emits_distinct_trace_id() -> None:
    """Two sequential calls must produce two distinct trace_ids."""
    v1 = await check_output_leak(CheckOutputLeakInputs(output_text="One."))
    v2 = await check_output_leak(CheckOutputLeakInputs(output_text="Two."))
    assert v1.trace_id != v2.trace_id


# --- BDD 12: sensitivity profile → enabled_rules mapping ----------------


@pytest.mark.parametrize(
    ("sensitivity", "expected"),
    [
        ("default", {"PII"}),
        ("fsi", {"PII", "PCI"}),
        ("hipaa", {"PII", "PHI"}),
        ("pubsec", {"PII"}),
    ],
)
async def test_sensitivity_profile_maps_to_enabled_rules(
    sensitivity: str,
    expected: set[str],
) -> None:
    """Each sensitivity profile maps to its documented enabled_rules list.

    Asserts the request body's `config.enabled_rules` matches the
    locked mapping in story spec lines 143-147. Uses respx with a
    benign safe-response so the routing path is exercised end-to-end
    without depending on rule-specific fixture content.
    """
    payload = {
        "is_safe": True,
        "severity": "NONE_SEVERITY",
        "classifications": [],
        "rules": [],
    }
    captured: dict[str, object] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", _FAKE_KEY)
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            route = router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            await check_output_leak(
                CheckOutputLeakInputs(
                    output_text="Plain inert text.",
                    sensitivity=sensitivity,  # type: ignore[arg-type]
                )
            )
            captured["body"] = route.calls.last.request.content
    body_bytes = captured["body"]
    assert isinstance(body_bytes, bytes)
    body = json.loads(body_bytes)
    rule_names = {r["rule_name"] for r in body["config"]["enabled_rules"]}
    assert rule_names == expected


# --- Bonus: round-trip schema validation -------------------------------


async def test_verdict_round_trip_validates_against_output_schema() -> None:
    """`Verdict.model_dump(mode='json')` validates under outputSchema."""
    import jsonschema  # noqa: PLC0415

    verdict = await check_output_leak(CheckOutputLeakInputs(output_text="benign text"))
    dumped = verdict.model_dump(mode="json")
    jsonschema.validate(instance=dumped, schema=VERDICT_OUTPUT_SCHEMA)


# --- silent-failure-hunter follow-up (PR #117 review) ------------------


async def test_redaction_miss_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AI Defense fires PII but our regex doesn't match → WARN logged.

    Per silent-failure-hunter BLOCKING finding on PR #117: when the
    InspectResponse contains a rule_name we have patterns for but
    none of the patterns match the actual output, `redacted_output`
    would equal the original text. Surface 4 dashboards would show
    green MODIFY tiles while sensitive content leaks downstream
    verbatim. The fix logs WARN so the regex-coverage gap is visible.
    """
    payload = {
        "is_safe": False,
        "severity": "LOW",
        "classifications": ["PRIVACY_VIOLATION"],
        "rules": [
            {
                "rule_name": "PII",
                "classification": "PRIVACY_VIOLATION",
                "entity_types": ["FOREIGN_ID"],
            }
        ],
        "explanation": "Detected non-US identifier we have no v1 redactor for.",
    }
    # Input has no substrings matching our PII patterns (no SSN
    # shape, no email, no US phone). AI Defense flags PII anyway.
    inert_text = "The customer's reference number is foo-bar-baz."
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SPLUNKGATE_AI_DEFENSE_API_KEY", "x")
        mp.delenv("SPLUNKGATE_AI_DEFENSE_MOCK", raising=False)
        with respx.mock() as router:
            router.post(_LIVE_URL).mock(return_value=httpx.Response(200, json=payload))
            with caplog.at_level("WARNING"):
                verdict = await check_output_leak(CheckOutputLeakInputs(output_text=inert_text))
    # MODIFY stands (AI Defense's word), but the WARN is the visibility signal
    assert verdict.verdict is VerdictLabel.MODIFY
    assert any("redaction.miss" in r.message for r in caplog.records), [
        r.message for r in caplog.records
    ]

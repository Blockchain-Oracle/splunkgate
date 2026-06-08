"""Behavioral tests for the Foundation-Sec `| ai` SPL explainer.

Covers:
- build_ai_spl() purity + canonical model/provider names
- prompt escape semantics (quotes, backslash, newline, length cap)
- mock-mode default + env-var toggle
- service-absent short-circuit
- live-mode delegation to splunklib.client.Service.jobs.oneshot
- exception path falls through to template explainer
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import structlog
from splunkgate_core import RuleHit, Severity, Verdict, VerdictContext, VerdictLabel
from splunkgate_judges.foundsec_spl import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MOCK_ENV_VAR,
    build_ai_spl,
    explain_via_ai_spl,
)

_FIXED_TIME = datetime(2026, 6, 8, 12, 0, 0, tzinfo=UTC)
_FIXED_UUID = uuid4()


def _verdict(
    *,
    label: VerdictLabel = VerdictLabel.BLOCK,
    severity: Severity = Severity.HIGH,
    rules: list[RuleHit] | None = None,
) -> Verdict:
    return Verdict(
        trace_id=_FIXED_UUID,
        timestamp=_FIXED_TIME,
        verdict=label,
        severity=severity,
        rules=rules
        if rules is not None
        else [RuleHit(rule="Prompt Injection", confidence=1.0, source="ai_defense")],
        surface="mw_model",
        latency_ms=12.5,
    )


def _ctx() -> VerdictContext:
    return VerdictContext(
        trace_id=_FIXED_UUID,
        agent_id="support-agent",
        model_name="claude-sonnet-4-6",
        system_prompt_summary="Customer support routing",
        recent_messages=["Hi"],
        surface="mw_model",
    )


# ---------- build_ai_spl (pure) ----------


def test_build_ai_spl_includes_canonical_provider_and_model() -> None:
    spl = build_ai_spl(_verdict())
    assert f"provider={DEFAULT_PROVIDER}" in spl
    assert f"model={DEFAULT_MODEL}" in spl
    # Verbatim model name per Splunk Hosted Models docs
    assert "foundation-sec-1.1-8b-instruct" in spl


def test_build_ai_spl_starts_with_makeresults_pipe() -> None:
    spl = build_ai_spl(_verdict())
    assert spl.startswith("| makeresults")


def test_build_ai_spl_routes_through_eval_then_ai_then_fields() -> None:
    """Pipeline order matters: makeresults → eval → ai → fields explanation."""
    spl = build_ai_spl(_verdict())
    idx_make = spl.find("| makeresults")
    idx_eval = spl.find("| eval prompt=")
    idx_ai = spl.find("| ai prompt=prompt")
    idx_fields = spl.find("| fields explanation")
    assert 0 == idx_make < idx_eval < idx_ai < idx_fields


def test_build_ai_spl_surfaces_rule_names_in_prompt() -> None:
    v = _verdict(
        rules=[
            RuleHit(rule="Prompt Injection", confidence=1.0, source="ai_defense"),
            RuleHit(rule="PII", confidence=0.9, source="ai_defense"),
        ]
    )
    spl = build_ai_spl(v)
    assert "Prompt Injection" in spl
    assert "PII" in spl


def test_build_ai_spl_surfaces_agent_id_when_ctx_provided() -> None:
    spl_no_ctx = build_ai_spl(_verdict())
    spl_with_ctx = build_ai_spl(_verdict(), _ctx())
    assert "support-agent" not in spl_no_ctx
    assert "support-agent" in spl_with_ctx


def test_build_ai_spl_is_deterministic_byte_equal() -> None:
    v = _verdict()
    assert build_ai_spl(v) == build_ai_spl(v)


def test_build_ai_spl_escapes_embedded_double_quote() -> None:
    """SPL injection guard — a rule with a `"` in its name must not break the eval."""
    v = _verdict(
        rules=[
            RuleHit(rule='evil"quoted"rule', confidence=1.0, source="ai_defense"),
        ]
    )
    spl = build_ai_spl(v)
    # Each raw " inside the prompt must be backslash-escaped (\")
    assert '\\"quoted\\"' in spl
    # And the OUTER `| eval prompt="..."` quotes must remain balanced —
    # count of unescaped quote marks must be exactly 2 (opening + closing).
    unescaped_quotes = spl.replace('\\"', "")
    assert unescaped_quotes.count('"') == 2, spl


def test_build_ai_spl_collapses_newlines_to_spaces() -> None:
    v = _verdict(
        rules=[
            RuleHit(rule="bad\nrule\nname", confidence=1.0, source="ai_defense"),
        ]
    )
    spl = build_ai_spl(v)
    # `| ai prompt=...` expects a single-line string; raw newlines break SPL.
    assert "\n" not in spl


def test_build_ai_spl_truncates_huge_prompts() -> None:
    huge_rule = "x" * 5000
    v = _verdict(rules=[RuleHit(rule=huge_rule, confidence=1.0, source="ai_defense")])
    spl = build_ai_spl(v)
    # Generous overall length cap, well clear of Splunk's SPL line limit
    assert len(spl) < 2000


def test_build_ai_spl_handles_zero_rules() -> None:
    v = _verdict(rules=[])
    spl = build_ai_spl(v)
    assert "no rules" in spl


# ---------- explain_via_ai_spl (integration + fallbacks) ----------


def test_explain_via_ai_spl_default_is_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default behavior (no env var set) must be template fallback."""
    monkeypatch.delenv(MOCK_ENV_VAR, raising=False)
    out = explain_via_ai_spl(_verdict(), _ctx())
    # Template explainer signature: "<LABEL> (severity <SEV>): <body>."
    assert "BLOCK" in out
    assert "HIGH" in out
    assert "Prompt Injection" in out


@pytest.mark.parametrize("truthy", ["true", "True", "1", "yes", "on", "Y"])
def test_explain_via_ai_spl_truthy_env_keeps_mock(
    truthy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MOCK_ENV_VAR, truthy)
    # A service is intentionally passed but mock-mode short-circuits before use
    bogus = MagicMock()
    out = explain_via_ai_spl(_verdict(), service=bogus)
    bogus.jobs.oneshot.assert_not_called()
    assert "BLOCK" in out


def test_explain_via_ai_spl_service_absent_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No service + live-mode env still falls back (we cannot call without auth)."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")
    out = explain_via_ai_spl(_verdict(), service=None)
    assert "BLOCK" in out


def test_explain_via_ai_spl_falls_back_on_service_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MOCK_ENV_VAR, "false")
    svc = MagicMock()
    svc.jobs.oneshot.side_effect = RuntimeError("splunk down")
    out = explain_via_ai_spl(_verdict(), service=svc)
    # Template fallback shape
    assert "BLOCK" in out
    assert "HIGH" in out


def test_explain_via_ai_spl_returns_live_explanation_when_service_responds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live happy path — service.jobs.oneshot returns a single row with explanation."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")

    # Patch JSONResultsReader to yield our canned row regardless of input
    fake_row: dict[str, Any] = {
        "explanation": "Foundation-Sec: multi-step prompt injection attempting PII exfiltration."
    }

    class _FakeReader:
        def __init__(self, _stream: object) -> None:
            self._rows = [fake_row]

        def __iter__(self) -> Any:
            return iter(self._rows)

    monkeypatch.setattr("splunklib.results.JSONResultsReader", _FakeReader)
    svc = MagicMock()
    svc.jobs.oneshot.return_value = b"unused"

    out = explain_via_ai_spl(_verdict(), service=svc)
    assert "Foundation-Sec" in out
    assert "prompt injection" in out.lower()
    # Make sure live path actually ran the SPL
    svc.jobs.oneshot.assert_called_once()
    call_args = svc.jobs.oneshot.call_args
    sent_spl = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
    assert "ai prompt=prompt provider=Splunk" in sent_spl


def test_explain_via_ai_spl_falls_back_when_live_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / null explanation from `| ai` must trigger template fallback."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")

    class _EmptyReader:
        def __init__(self, _stream: object) -> None:
            self._rows: list[dict[str, str]] = [{"explanation": "  "}]

        def __iter__(self) -> Any:
            return iter(self._rows)

    monkeypatch.setattr("splunklib.results.JSONResultsReader", _EmptyReader)
    svc = MagicMock()
    svc.jobs.oneshot.return_value = b"unused"

    out = explain_via_ai_spl(_verdict(), service=svc)
    # Template fallback
    assert "BLOCK" in out
    assert "HIGH" in out


# ---------- structlog observability (silent-failure-hunter follow-up) ----------
# Use structlog.testing.capture_logs() — the canonical pytest pattern for
# structlog assertions. caplog only sees stdlib logging records, but our
# convention (matching splunkgate_judges/ai_defense.py) uses structlog.


def test_mock_mode_logs_info_when_service_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock-mode default: log an info event so operators see the mode in use."""
    monkeypatch.delenv(MOCK_ENV_VAR, raising=False)
    with structlog.testing.capture_logs() as records:
        explain_via_ai_spl(_verdict())
    events = [(r.get("event"), r.get("mode")) for r in records]
    assert ("splunkgate.explainer.mode", "mock") in events, events


def test_mock_mode_warns_when_service_was_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator passed a service but mock mode silently ignored it — log loud."""
    monkeypatch.setenv(MOCK_ENV_VAR, "true")
    svc = MagicMock()
    with structlog.testing.capture_logs() as records:
        explain_via_ai_spl(_verdict(), service=svc)
    svc.jobs.oneshot.assert_not_called()
    events = [r.get("event") for r in records]
    assert "splunkgate.explainer.service_ignored_in_mock_mode" in events, events


def test_live_mode_logs_warning_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live-call exceptions must be visible — exception class + message logged."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")
    svc = MagicMock()
    svc.jobs.oneshot.side_effect = RuntimeError("splunk auth failed")
    with structlog.testing.capture_logs() as records:
        explain_via_ai_spl(_verdict(), service=svc)
    matched = [r for r in records if r.get("event") == "splunkgate.explainer.live_call_failed"]
    assert matched, [r.get("event") for r in records]
    assert matched[0].get("exc_class") == "RuntimeError"
    assert matched[0].get("exc_msg") == "splunk auth failed"


def test_live_mode_logs_warning_when_no_explanation_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrong field name in `| ai` response: log the row keys for debug."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")

    class _WrongFieldReader:
        def __init__(self, _stream: object) -> None:
            self._rows: list[dict[str, str]] = [{"result": "wrong field name"}]

        def __iter__(self) -> Any:
            return iter(self._rows)

    monkeypatch.setattr("splunklib.results.JSONResultsReader", _WrongFieldReader)
    svc = MagicMock()
    svc.jobs.oneshot.return_value = b"unused"
    with structlog.testing.capture_logs() as records:
        explain_via_ai_spl(_verdict(), service=svc)
    matched = [
        r for r in records if r.get("event") == "splunkgate.explainer.no_explanation_in_response"
    ]
    assert matched, [r.get("event") for r in records]
    assert matched[0].get("row_keys") == ["result"]


def test_live_mode_no_service_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live mode requested but service=None — operator should be told."""
    monkeypatch.setenv(MOCK_ENV_VAR, "false")
    with structlog.testing.capture_logs() as records:
        explain_via_ai_spl(_verdict(), service=None)
    events = [r.get("event") for r in records]
    assert "splunkgate.explainer.live_no_service" in events, events

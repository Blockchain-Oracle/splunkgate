"""Behavioral tests for the AI Defense Pydantic models.

Source of truth for the schema:
  ../../../../context/07-cisco-stack/01-ai-defense-deep.md (§§ 5-7)
"""

import pytest
from aegis_core.verdict import Severity
from aegis_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    EnabledRule,
    InspectConfig,
    InspectMessage,
    InspectRequest,
    InspectResponse,
    RuleHit,
)
from pydantic import ValidationError

# The 11 canonical rule names verbatim per docs § 7. ANY deviation here is
# a real spec drift — this constant is the test-side spec witness.
CANONICAL_11_RULES = {
    "Code Detection",
    "Harassment",
    "Hate Speech",
    "PCI",
    "PHI",
    "PII",
    "Prompt Injection",
    "Profanity",
    "Sexual Content & Exploitation",
    "Social Division & Polarization",
    "Violence & Public Safety Threats",
}


def test_ai_defense_rule_has_exactly_11_canonical_names() -> None:
    actual = {r.value for r in AIDefenseRule}
    assert actual == CANONICAL_11_RULES, (
        f"AI Defense rule set diverged from public docs: "
        f"missing={CANONICAL_11_RULES - actual}, extra={actual - CANONICAL_11_RULES}"
    )


def test_severity_includes_none_severity() -> None:
    assert "NONE_SEVERITY" in {s.value for s in Severity}


def test_severity_has_exactly_four_values() -> None:
    assert {s.value for s in Severity} == {"NONE_SEVERITY", "LOW", "MEDIUM", "HIGH"}


def test_inspect_response_has_rules_field_not_triggered_rules() -> None:
    """Compile-time gate against the historical `triggered_rules` hallucination."""
    fields = set(InspectResponse.model_fields.keys())
    assert "rules" in fields
    assert "triggered_rules" not in fields


def test_classifications_enum_has_all_four_categories() -> None:
    assert {c.value for c in Classification} == {
        "SECURITY_VIOLATION",
        "PRIVACY_VIOLATION",
        "SAFETY_VIOLATION",
        "RELEVANCE_VIOLATION",
    }


def test_inspect_request_round_trips_through_json() -> None:
    req = InspectRequest(
        messages=[InspectMessage(role="user", content="My ssn is 123-45-6789")],
        metadata={"user_id": "u1", "app_id": "demo"},
        config=InspectConfig(enabled_rules=[EnabledRule(rule_name=AIDefenseRule.PII)]),
    )
    restored = InspectRequest.model_validate_json(req.model_dump_json())
    assert restored == req


def test_inspect_response_round_trips_with_full_payload() -> None:
    resp = InspectResponse(
        is_safe=False,
        severity=Severity.HIGH,
        classifications=[Classification.SECURITY_VIOLATION, Classification.PRIVACY_VIOLATION],
        rules=[
            RuleHit(
                rule_name=AIDefenseRule.PII,
                classification=Classification.PRIVACY_VIOLATION,
                entity_types=["SSN"],
            )
        ],
        attack_technique="data_exfiltration",
        explanation="The user message contains a US Social Security Number.",
        event_id="evt_abc123",
        client_transaction_id="tx_xyz",
    )
    restored = InspectResponse.model_validate_json(resp.model_dump_json())
    assert restored == resp
    # Sample payload from the Cisco docs verbatim — confirm we can parse it.
    sample = (
        '{"is_safe": false, "severity": "HIGH", '
        '"classifications": ["SECURITY_VIOLATION", "PRIVACY_VIOLATION"], '
        '"rules": [{"rule_name": "PII", "classification": "PRIVACY_VIOLATION", '
        '"entity_types": ["SSN"]}], '
        '"attack_technique": "data_exfiltration", '
        '"explanation": "The user message contains a US Social Security Number.", '
        '"event_id": "evt_x", "client_transaction_id": "tx_y"}'
    )
    parsed = InspectResponse.model_validate_json(sample)
    assert parsed.is_safe is False
    assert parsed.severity is Severity.HIGH


def test_inspect_response_accepts_minimal_safe_payload() -> None:
    resp = InspectResponse(is_safe=True, severity=Severity.NONE_SEVERITY)
    assert resp.is_safe is True
    assert resp.severity is Severity.NONE_SEVERITY
    assert resp.rules == []
    assert resp.classifications == []
    assert resp.explanation is None


def test_inspect_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        InspectRequest(messages=[])


def test_inspect_request_rejects_unknown_field() -> None:
    """extra=forbid catches typos that Cisco's strict parser would reject."""
    with pytest.raises(ValidationError):
        InspectRequest.model_validate(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "unknown_field": "should fail",
            }
        )


def test_inspect_message_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        InspectMessage(role="hacker", content="x")  # type: ignore[arg-type]


def test_rule_hit_rejects_unknown_rule_name() -> None:
    """The 11 canonical rules are the only accepted rule_name values."""
    with pytest.raises(ValidationError):
        RuleHit.model_validate(
            {
                "rule_name": "Jailbreak",  # DefenseClaw-only; not in public docs
                "classification": "SECURITY_VIOLATION",
                "entity_types": [],
            }
        )


def test_rule_hit_rejects_unknown_classification() -> None:
    with pytest.raises(ValidationError):
        RuleHit.model_validate(
            {
                "rule_name": "PII",
                "classification": "UNKNOWN_VIOLATION",
                "entity_types": [],
            }
        )


def test_inspect_config_empty_is_valid() -> None:
    """Empty config means 'apply all default-enabled rules for the API key'."""
    cfg = InspectConfig()
    assert cfg.enabled_rules is None
    assert cfg.integration_profile_id is None


def test_inspect_config_accepts_integration_profile_shape() -> None:
    cfg = InspectConfig(
        integration_profile_id="ip-1",
        integration_profile_version="v1",
        integration_tenant_id="t1",
        integration_type="custom",
    )
    assert cfg.integration_profile_id == "ip-1"


def test_canonical_rule_strings_match_test_witness() -> None:
    """Test-side spec witness: if the AIDefenseRule values drift from the
    documented 11, this test surfaces the drift before downstream stories
    serialize the wrong name into a live API call."""
    documented = sorted(CANONICAL_11_RULES)
    enumerated = sorted(r.value for r in AIDefenseRule)
    assert enumerated == documented

"""Behavioral tests for MockAIDefenseClient + AIDefenseClient.from_env() factory."""

import pytest
from aegis_judges._errors import AIDefenseAuthError
from aegis_judges._fixtures import load_fixture_matrix, load_trigger_table
from aegis_judges.ai_defense import AIDefenseClient
from aegis_judges.ai_defense_mock import MockAIDefenseClient
from aegis_judges.ai_defense_types import (
    AIDefenseRule,
    InspectMessage,
    InspectRequest,
    Severity,
)

EXPECTED_RULE_NAMES = {r.value for r in AIDefenseRule}
EXPECTED_SEVERITIES = {"NONE_SEVERITY", "LOW", "MEDIUM", "HIGH"}


def _request(text: str) -> InspectRequest:
    return InspectRequest(messages=[InspectMessage(role="user", content=text)])


def test_matrix_has_exactly_44_rows() -> None:
    matrix = load_fixture_matrix()
    assert len(matrix) == 44


def test_matrix_covers_all_11_canonical_rules() -> None:
    matrix = load_fixture_matrix()
    found_rules = set()
    for entry in matrix:
        for r in entry.rules:
            found_rules.add(r.rule_name.value)
    # NONE_SEVERITY rows have rules=[], so we only check non-safe rows.
    # All 11 rules MUST appear in the non-safe tiers.
    assert found_rules == EXPECTED_RULE_NAMES


def test_matrix_covers_all_4_severities() -> None:
    matrix = load_fixture_matrix()
    severities = {entry.severity.value for entry in matrix}
    assert severities == EXPECTED_SEVERITIES


def test_trigger_table_has_44_unique_entries() -> None:
    triggers = load_trigger_table()
    assert len(triggers) == 44
    assert len(set(triggers.values())) == 44  # 44 distinct indices


@pytest.mark.asyncio
async def test_mock_dispatch_is_deterministic_on_known_trigger(
    ai_defense_mock: MockAIDefenseClient,
) -> None:
    triggers = load_trigger_table()
    trigger = next(iter(triggers))
    r1 = await ai_defense_mock.inspect_chat(_request(trigger))
    r2 = await ai_defense_mock.inspect_chat(_request(trigger))
    assert r1.model_dump_json() == r2.model_dump_json()


@pytest.mark.asyncio
async def test_mock_dispatch_known_trigger_returns_expected_rule(
    ai_defense_mock: MockAIDefenseClient,
) -> None:
    # PII trigger should map to a PII rule fixture.
    triggers = load_trigger_table()
    pii_trigger = next(t for t in triggers if t.startswith("my ssn is 123-45-6789"))
    response = await ai_defense_mock.inspect_chat(_request(pii_trigger))
    if response.rules:
        assert response.rules[0].rule_name is AIDefenseRule.PII


@pytest.mark.asyncio
async def test_mock_empty_text_returns_default_safe(
    ai_defense_mock: MockAIDefenseClient,
) -> None:
    response = await ai_defense_mock.inspect_chat(_request("   "))
    assert response.is_safe is True
    assert response.severity is Severity.NONE_SEVERITY
    assert response.rules == []


@pytest.mark.asyncio
async def test_mock_unknown_text_dispatches_deterministically(
    ai_defense_mock: MockAIDefenseClient,
) -> None:
    """Hash-bucketing produces the same fixture for the same unknown text."""
    unknown = "this is some random text that does not match any trigger string"
    r1 = await ai_defense_mock.inspect_chat(_request(unknown))
    r2 = await ai_defense_mock.inspect_chat(_request(unknown))
    assert r1.model_dump_json() == r2.model_dump_json()


@pytest.mark.asyncio
async def test_mock_async_context_manager_works() -> None:
    async with MockAIDefenseClient() as c:
        response = await c.inspect_chat(_request("hello"))
        assert response.severity in Severity


def test_from_env_returns_mock_when_aegis_ai_defense_mock_truthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGIS_AI_DEFENSE_MOCK", "1")
    client = AIDefenseClient.from_env()
    assert type(client).__name__ == "MockAIDefenseClient"


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_from_env_accepts_multiple_truthy_spellings(
    monkeypatch: pytest.MonkeyPatch, truthy: str
) -> None:
    monkeypatch.setenv("AEGIS_AI_DEFENSE_MOCK", truthy)
    client = AIDefenseClient.from_env()
    assert type(client).__name__ == "MockAIDefenseClient"


def test_from_env_raises_auth_error_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AEGIS_AI_DEFENSE_MOCK", raising=False)
    monkeypatch.delenv("AEGIS_AI_DEFENSE_API_KEY", raising=False)
    with pytest.raises(AIDefenseAuthError, match="AEGIS_AI_DEFENSE_API_KEY"):
        AIDefenseClient.from_env()


def test_from_env_uses_live_client_when_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGIS_AI_DEFENSE_API_KEY", "synth-test-key-12345")
    client = AIDefenseClient.from_env()
    assert type(client).__name__ == "AIDefenseClient"


def test_from_env_respects_region_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGIS_AI_DEFENSE_API_KEY", "synth-test-key-12345")
    monkeypatch.setenv("AEGIS_AI_DEFENSE_REGION", "eu")
    client = AIDefenseClient.from_env()
    assert isinstance(client, AIDefenseClient)
    assert "eu.api.inspect" in client._url  # noqa: SLF001 — test seam


def test_from_env_invalid_region_falls_back_to_us(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGIS_AI_DEFENSE_API_KEY", "synth-test-key-12345")
    monkeypatch.setenv("AEGIS_AI_DEFENSE_REGION", "atlantis")
    client = AIDefenseClient.from_env()
    assert isinstance(client, AIDefenseClient)
    assert "us.api.inspect" in client._url  # noqa: SLF001 — test seam

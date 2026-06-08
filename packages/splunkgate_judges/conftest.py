"""Test session config for splunkgate_judges — mock client fixture + env reset."""

import pytest
from splunkgate_judges.ai_defense_mock import MockAIDefenseClient

_SPLUNKGATE_ENV_VARS = (
    "SPLUNKGATE_AI_DEFENSE_MOCK",
    "SPLUNKGATE_AI_DEFENSE_API_KEY",
    "SPLUNKGATE_AI_DEFENSE_REGION",
)


@pytest.fixture
def ai_defense_mock() -> MockAIDefenseClient:
    """Return a fresh MockAIDefenseClient per test."""
    return MockAIDefenseClient()


@pytest.fixture(autouse=True)
def _reset_aidefense_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe SPLUNKGATE_AI_DEFENSE_* env vars before each test for isolation."""
    for var in _SPLUNKGATE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

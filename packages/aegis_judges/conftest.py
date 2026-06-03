"""Test session config for aegis_judges — mock client fixture + env reset."""

import pytest
from aegis_judges.ai_defense_mock import MockAIDefenseClient

_AEGIS_ENV_VARS = (
    "AEGIS_AI_DEFENSE_MOCK",
    "AEGIS_AI_DEFENSE_API_KEY",
    "AEGIS_AI_DEFENSE_REGION",
)


@pytest.fixture
def ai_defense_mock() -> MockAIDefenseClient:
    """Return a fresh MockAIDefenseClient per test."""
    return MockAIDefenseClient()


@pytest.fixture(autouse=True)
def _reset_aidefense_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe AEGIS_AI_DEFENSE_* env vars before each test for isolation."""
    for var in _AEGIS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

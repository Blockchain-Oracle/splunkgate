"""Smoke tests — `examples/support_agent.py` builds the Agent with all 4 middleware (story-mw-07)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from splunkgate_mw import (
    FINANCIAL_SERVICES_PROFILE,
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from splunklib.ai import Agent

if TYPE_CHECKING:
    from types import ModuleType

    from splunklib.ai.middleware import AgentMiddleware

DEMO_PATH = Path(__file__).parent.parent / "examples" / "support_agent.py"
REQUIRED_MIDDLEWARE = (
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)


def _load_demo() -> ModuleType:
    """Import support_agent.py as a module without exec'ing main()."""
    spec = importlib.util.spec_from_file_location("support_agent", DEMO_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed the env vars the demo reads, then no-op the Splunk connect() call.

    `splunklib.client.connect()` does a network handshake — the demo
    smoke tests must NOT hit a real Splunk host. We patch it at the
    module's import site so build_agent() runs end-to-end against a
    sentinel Service object.
    """
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_HOST", "splunk.example.com")
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_PORT", "8089")
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_TOKEN", "test-session-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")


def test_demo_imports_without_error() -> None:
    """Importing the demo must not crash — no top-level connect()/Agent construction."""
    module = _load_demo()
    assert hasattr(module, "build_agent")
    assert hasattr(module, "main")
    assert module.PROFILE == "financial_services"


@pytest.mark.usefixtures("demo_env")
def test_build_agent_constructs_with_all_four_middleware_instances() -> None:
    """The Agent receives a middleware sequence with one instance of each SplunkGate class."""
    module = _load_demo()
    with patch.object(module, "connect", return_value=object()):
        agent: Agent[None] = module.build_agent()
    middleware = agent.middleware or []
    classes_on_agent = {type(m) for m in middleware}
    for cls in REQUIRED_MIDDLEWARE:
        assert cls in classes_on_agent, f"{cls.__name__} not on the demo Agent"


@pytest.mark.usefixtures("demo_env")
def test_every_middleware_carries_financial_services_profile() -> None:
    """The single profile string flows through to all 4 middleware instances."""
    module = _load_demo()
    with patch.object(module, "connect", return_value=object()):
        agent: Agent[None] = module.build_agent()
    splunkgate_instances: list[AgentMiddleware] = [
        m for m in (agent.middleware or []) if isinstance(m, REQUIRED_MIDDLEWARE)
    ]
    assert len(splunkgate_instances) == 4
    for m in splunkgate_instances:
        assert m._profile is FINANCIAL_SERVICES_PROFILE  # noqa: SLF001 — testing the wedge contract


@pytest.mark.usefixtures("demo_env")
def test_demo_uses_real_splunklib_ai_agent_class() -> None:
    """Defensive: the demo isn't an over-mocked shim — it really builds splunklib.ai.Agent."""
    module = _load_demo()
    with patch.object(module, "connect", return_value=object()):
        agent = module.build_agent()
    assert isinstance(agent, Agent)

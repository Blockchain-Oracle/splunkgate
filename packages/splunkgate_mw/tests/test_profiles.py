"""Behavioural tests for the 4 canonical profiles + resolve_profile (story-mw-07)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError
from splunkgate_core.errors import UnknownProfile
from splunkgate_mw import (
    DEFAULT_PROFILE,
    FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE,
    PUBLIC_SECTOR_PROFILE,
    Profile,
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
    resolve_profile,
)

ALL_PROFILES = (
    DEFAULT_PROFILE,
    FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE,
    PUBLIC_SECTOR_PROFILE,
)
MIDDLEWARE_CLASSES = (
    SafetyToolMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyAgentMiddleware,
)


def test_all_four_profile_names_are_canonical() -> None:
    """BDD criterion 1 — exactly these four names exist."""
    assert sorted(p.name for p in ALL_PROFILES) == [
        "default",
        "financial_services",
        "healthcare",
        "public_sector",
    ]


def test_all_profiles_are_frozen_pydantic_models() -> None:
    """frozen=True is non-negotiable — Profile assignments must raise."""
    for p in ALL_PROFILES:
        with pytest.raises((PydanticValidationError, AttributeError, TypeError)):
            p.name = "default"  # type: ignore[misc]


def test_all_profiles_are_hashable() -> None:
    """Hashable = usable as dict keys / set members (caches, override maps)."""
    for p in ALL_PROFILES:
        hash(p)
    assert len({hash(p) for p in ALL_PROFILES}) == len(ALL_PROFILES)


def test_profile_rejects_unknown_name_literal() -> None:
    """Pydantic Literal validation catches typos at construction time."""
    with pytest.raises(PydanticValidationError):
        Profile(name="banking", description="...")  # type: ignore[arg-type]


def test_profile_rejects_extra_fields() -> None:
    """extra='forbid' catches accidental field typos at construction time."""
    with pytest.raises(PydanticValidationError):
        Profile(name="default", description="...", surprise=True)  # type: ignore[call-arg]


def test_financial_services_profile_has_pci_in_both_rule_subsets() -> None:
    """BDD criterion 4 — PCI in rules_post_inference AND rules_tool_call."""
    assert "PCI" in FINANCIAL_SERVICES_PROFILE.rules_post_inference
    assert "PCI" in FINANCIAL_SERVICES_PROFILE.rules_tool_call


def test_financial_services_profile_lists_sensitive_data() -> None:
    """FSI distinctive marker — Sensitive Data appears in post_inference."""
    assert "Sensitive Data" in FINANCIAL_SERVICES_PROFILE.rules_post_inference


def test_healthcare_profile_has_phi_in_both_rule_subsets() -> None:
    """BDD criterion 5 — PHI in rules_post_inference AND rules_tool_call."""
    assert "PHI" in HEALTHCARE_PROFILE.rules_post_inference
    assert "PHI" in HEALTHCARE_PROFILE.rules_tool_call


def test_public_sector_profile_includes_code_detection() -> None:
    """BDD criterion 6 — Code Detection in rules_post_inference."""
    assert "Code Detection" in PUBLIC_SECTOR_PROFILE.rules_post_inference


def test_public_sector_profile_includes_content_classification_rules() -> None:
    """PubSec distinctive marker — content-classification rules surface."""
    rules = PUBLIC_SECTOR_PROFILE.rules_post_inference
    assert "Violence & Public Safety Threats" in rules
    assert "Social Division & Polarization" in rules


def test_default_profile_has_balanced_rule_subsets() -> None:
    """Default profile includes the core 4 categories — PII / PHI / PCI / Code."""
    rules = DEFAULT_PROFILE.rules_post_inference
    assert set(rules) >= {"PII", "PHI", "PCI", "Code Detection"}


def test_all_profiles_escalate_on_first_pass_hit() -> None:
    """Cheap-first-pass-then-AI-Defense is the default for every profile."""
    for p in ALL_PROFILES:
        assert p.escalate_on_first_pass_hit is True


def test_all_profiles_have_prompt_injection_in_pre_inference() -> None:
    """Pre-inference scan always catches Prompt Injection."""
    for p in ALL_PROFILES:
        assert "Prompt Injection" in p.rules_pre_inference


def test_resolve_profile_by_canonical_string_returns_singleton() -> None:
    """resolve_profile('financial_services') returns the module-level constant."""
    assert resolve_profile("financial_services") is FINANCIAL_SERVICES_PROFILE
    assert resolve_profile("healthcare") is HEALTHCARE_PROFILE
    assert resolve_profile("public_sector") is PUBLIC_SECTOR_PROFILE
    assert resolve_profile("default") is DEFAULT_PROFILE


def test_resolve_profile_is_identity_on_profile_instances() -> None:
    """Passing a Profile through resolve_profile returns the same object."""
    custom = Profile(name="default", description="custom-default fixture")
    assert resolve_profile(custom) is custom
    assert resolve_profile(FINANCIAL_SERVICES_PROFILE) is FINANCIAL_SERVICES_PROFILE


def test_resolve_profile_unknown_name_raises_unknown_profile() -> None:
    """BDD criterion 3 — unknown names raise UnknownProfile, not KeyError."""
    with pytest.raises(UnknownProfile) as exc_info:
        resolve_profile("banking")
    assert exc_info.value.name == "banking"
    assert "banking" in str(exc_info.value)


def test_all_four_middleware_receive_the_same_profile_via_string() -> None:
    """The 3-line wedge — one profile string lands on every middleware's `._profile`."""
    instances = [cls(profile="financial_services") for cls in MIDDLEWARE_CLASSES]
    for instance in instances:
        assert instance._profile is FINANCIAL_SERVICES_PROFILE  # noqa: SLF001 — testing the wedge contract


def test_all_four_middleware_receive_the_same_profile_via_object() -> None:
    """Profile object identity flows through all 4 middleware constructors."""
    instances = [cls(profile=HEALTHCARE_PROFILE) for cls in MIDDLEWARE_CLASSES]
    for instance in instances:
        assert instance._profile is HEALTHCARE_PROFILE  # noqa: SLF001 — testing the wedge contract


def test_middleware_constructors_reject_unknown_profile_string() -> None:
    """resolve_profile() at the boundary surfaces typos at construction time."""
    for cls in MIDDLEWARE_CLASSES:
        with pytest.raises(UnknownProfile):
            cls(profile="banking")


def test_support_agent_demo_body_under_30_loc() -> None:
    """BDD criterion 7 — demo body grep ≤30 lines."""
    demo = Path(__file__).parent.parent / "examples" / "support_agent.py"
    body_lines = [
        line
        for line in demo.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "from ", "import "))
    ]
    assert len(body_lines) <= 30, (
        f"support_agent.py body is {len(body_lines)} non-blank non-comment non-import lines"
    )

"""SplunkGate safety profiles — DEFAULT / FSI / HIPAA / PUBSEC.

A profile bundles four things into one knob the agent developer passes once:
1. Which AI Defense Inspection rule subset the model + tool layers care about.
2. Whether the cheap first-pass (`splunklib.ai.security`) is allowed to
   short-circuit before AI Defense escalation (`escalate_on_first_pass_hit`).
3. Whether Foundation-Sec explainer enrichment runs after a BLOCK
   (`foundation_sec_enabled`).
4. The human label that ships on every Verdict so SOC analysts can
   filter `splunkgate.profile=financial_services` in Splunk.

The 11 canonical Cisco AI Defense rule names are verbatim per
`../../../context/07-cisco-stack/01-ai-defense-deep.md` § 7:
    Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity,
    Prompt Injection, Sexual Content & Exploitation,
    Social Division & Polarization, Violence & Public Safety Threats.

The FSI + PubSec profiles also list "Sensitive Data" — that rule is
supplied by the DefenseClaw rule pack and is a no-op at the AI Defense
Inspection API layer; `splunkgate_judges.ai_defense.AIDefenseClient`
silently drops unknown rule names.

Pydantic `frozen=True` + `tuple[str, ...]` rule sets make profiles
hashable so they can be keys in caches / sets without surprise mutation.
"""

from __future__ import annotations

from typing import Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict
from splunkgate_core.errors import UnknownProfile

_logger = structlog.get_logger(__name__)

__all__ = [
    "DEFAULT_PROFILE",
    "FINANCIAL_SERVICES_PROFILE",
    "HEALTHCARE_PROFILE",
    "PUBLIC_SECTOR_PROFILE",
    "Profile",
    "log_if_custom_profile_shadows_canonical",
    "resolve_profile",
]

ProfileName = Literal["default", "financial_services", "healthcare", "public_sector"]


class Profile(BaseModel):
    """Frozen safety profile — name, description, and rule subset wedge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ProfileName
    description: str
    rules_pre_inference: tuple[str, ...] = ("Prompt Injection",)
    rules_post_inference: tuple[str, ...] = ("PII", "PHI", "PCI", "Code Detection")
    rules_tool_call: tuple[str, ...] = ("Prompt Injection", "Code Detection")
    escalate_on_first_pass_hit: bool = True
    foundation_sec_enabled: bool = True


DEFAULT_PROFILE: Final[Profile] = Profile(
    name="default",
    description="Balanced safety defaults; no domain-specific tuning.",
)

FINANCIAL_SERVICES_PROFILE: Final[Profile] = Profile(
    name="financial_services",
    description=(
        "Financial-services tuning — PCI / Sensitive-Data emphasis. "
        "'Sensitive Data' is supplied by the DefenseClaw rule pack and "
        "is a no-op at the AI Defense Inspection API layer."
    ),
    rules_post_inference=("PCI", "PII", "Code Detection", "Sensitive Data"),
    rules_tool_call=("Prompt Injection", "PCI", "Code Detection"),
)

HEALTHCARE_PROFILE: Final[Profile] = Profile(
    name="healthcare",
    description="HIPAA Safe-Harbor tuning — PHI emphasis.",
    rules_post_inference=("PHI", "PII", "Code Detection"),
    rules_tool_call=("Prompt Injection", "PHI"),
)

PUBLIC_SECTOR_PROFILE: Final[Profile] = Profile(
    name="public_sector",
    description=(
        "Public-sector tuning — compliance + content-classification "
        "emphasis. 'Sensitive Data' is DefenseClaw-only."
    ),
    rules_post_inference=(
        "PII",
        "Code Detection",
        "Violence & Public Safety Threats",
        "Social Division & Polarization",
    ),
    rules_tool_call=("Prompt Injection", "Code Detection"),
)


_BY_NAME: Final[dict[str, Profile]] = {
    DEFAULT_PROFILE.name: DEFAULT_PROFILE,
    FINANCIAL_SERVICES_PROFILE.name: FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE.name: HEALTHCARE_PROFILE,
    PUBLIC_SECTOR_PROFILE.name: PUBLIC_SECTOR_PROFILE,
}


def resolve_profile(name_or_profile: str | Profile) -> Profile:
    """Return the canonical Profile for a name or pass a Profile through.

    Passing a `Profile` instance is the identity — same object back.
    Passing a string looks the profile up in the canonical registry;
    unknown names raise `UnknownProfile` carrying the live valid-name
    tuple so a typo surfaces at construction time rather than silently
    degrading to defaults.
    """
    if isinstance(name_or_profile, Profile):
        return name_or_profile
    try:
        return _BY_NAME[name_or_profile]
    except KeyError as exc:
        raise UnknownProfile(name_or_profile, valid=tuple(_BY_NAME)) from exc


def log_if_custom_profile_shadows_canonical(profile: Profile, *, owner: str) -> None:
    """Log a warning when a Profile instance claims a canonical name but differs from the singleton.

    A regulated-industry deployment that constructs
    `Profile(name="healthcare", rules_post_inference=())` to "customise"
    HIPAA wedge produces a Verdict with `splunkgate.profile=healthcare`
    in Splunk while sending an empty rule set to AI Defense — the SOC
    dashboard claims an enforcement posture that does not exist. This
    helper does not block the construction (legitimate per-tenant
    overrides exist) but emits a single warning at middleware
    `__init__` so the divergence lands in the structlog stream and
    operators can audit it. `owner` is the middleware class name so the
    log line is easy to filter on.
    """
    canonical = _BY_NAME.get(profile.name)
    if canonical is None or canonical is profile:
        return
    drift_fields: dict[str, object] = {}
    for field in (
        "rules_pre_inference",
        "rules_post_inference",
        "rules_tool_call",
        "escalate_on_first_pass_hit",
        "foundation_sec_enabled",
    ):
        canonical_value = getattr(canonical, field)
        profile_value = getattr(profile, field)
        if canonical_value != profile_value:
            drift_fields[field] = {"canonical": canonical_value, "profile": profile_value}
    if drift_fields:
        _logger.warning(
            "profile.custom_instance_shadows_canonical_name",
            owner=owner,
            profile=profile.name,
            drift=drift_fields,
        )

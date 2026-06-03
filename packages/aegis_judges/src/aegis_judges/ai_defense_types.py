"""Cisco AI Defense Inspection API request/response Pydantic v2 models.

Mirrors the schema documented at:
  https://developer.cisco.com/docs/ai-defense-inspection/inspect-conversations/
(verified 2026-06-02; primary-source-grounded per
 ../../../context/07-cisco-stack/01-ai-defense-deep.md)

Key invariants enforced by these types:
- Response field is `rules` — NOT `triggered_rules`. The latter was an
  earlier-research hallucination logged in ../../../context/HALLUCINATION-AUDIT.md
  and ../../../context/07-cisco-stack/HALLUCINATION-AUDIT.md (H1).
- Severity enum includes NONE_SEVERITY alongside LOW/MEDIUM/HIGH.
- The 11 canonical rule names are verbatim per § 7 of the deep-dive
  (Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection,
   Profanity, Sexual Content & Exploitation, Social Division & Polarization,
   Violence & Public Safety Threats).

DefenseClaw's `cisco_inspect.go` line 38-51 hard-codes 12 names that don't
fully match the public 11 (DefenseClaw adds Jailbreak / Sensitive Data /
Data Leakage; lacks PCI / PHI). That contradiction is logged in the
context corpus and will be resolved by a live-API call in a later story.
This module uses the public-docs 11 only.
"""

from enum import StrEnum
from typing import Literal

from aegis_core.verdict import Severity
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AIDefenseRule",
    "Classification",
    "EnabledRule",
    "InspectConfig",
    "InspectMessage",
    "InspectRequest",
    "InspectResponse",
    "RuleHit",
    "Severity",
]


class AIDefenseRule(StrEnum):
    """The 11 canonical Cisco AI Defense Inspection rules (verbatim per docs § 7)."""

    CODE_DETECTION = "Code Detection"
    HARASSMENT = "Harassment"
    HATE_SPEECH = "Hate Speech"
    PCI = "PCI"
    PHI = "PHI"
    PII = "PII"
    PROMPT_INJECTION = "Prompt Injection"
    PROFANITY = "Profanity"
    SEXUAL_CONTENT_AND_EXPLOITATION = "Sexual Content & Exploitation"
    SOCIAL_DIVISION_AND_POLARIZATION = "Social Division & Polarization"
    VIOLENCE_AND_PUBLIC_SAFETY_THREATS = "Violence & Public Safety Threats"


class Classification(StrEnum):
    """Violation categories returned in InspectResponse.classifications."""

    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    PRIVACY_VIOLATION = "PRIVACY_VIOLATION"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    RELEVANCE_VIOLATION = "RELEVANCE_VIOLATION"


class InspectMessage(BaseModel):
    """A single chat message in the Inspection API request."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class EnabledRule(BaseModel):
    """An entry in `config.enabled_rules` referencing one canonical rule name."""

    model_config = ConfigDict(extra="forbid")

    rule_name: AIDefenseRule


class InspectConfig(BaseModel):
    """Inspection config — either `enabled_rules` OR integration_profile_*.

    The API treats both shapes as valid but mutually exclusive. We allow
    both as optional; the live API rejects ambiguous payloads. An empty
    `InspectConfig()` means "apply all default-enabled rules for the key."
    """

    model_config = ConfigDict(extra="forbid")

    enabled_rules: list[EnabledRule] | None = None
    integration_profile_id: str | None = None
    integration_profile_version: str | None = None
    integration_tenant_id: str | None = None
    integration_type: str | None = None


class InspectRequest(BaseModel):
    """POST /api/v1/inspect/chat request body."""

    model_config = ConfigDict(extra="forbid")

    messages: list[InspectMessage] = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)
    config: InspectConfig = Field(default_factory=InspectConfig)


class RuleHit(BaseModel):
    """A single triggered rule inside an InspectResponse.

    Response models use `extra="ignore"` (Pydantic default kept explicit)
    rather than `extra="forbid"`. Rationale: Cisco may add non-breaking
    fields server-side; rejecting them would hard-fail us in production
    for additions that should be transparent. Tradeoff: silent schema
    drift. judges-02's live-API smoke test surfaces drift early enough.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    rule_name: AIDefenseRule
    classification: Classification
    entity_types: list[str] = Field(default_factory=list)


class InspectResponse(BaseModel):
    """POST /api/v1/inspect/chat response body.

    Field name is `rules`, NOT `triggered_rules` — the earlier-research
    hallucination is gated at the type system level. Uses `extra="ignore"`
    for forward-compat with Cisco-side schema additions; request models
    keep `extra="forbid"` so OUR typos still fail validation.
    """

    model_config = ConfigDict(extra="ignore")

    is_safe: bool
    severity: Severity
    classifications: list[Classification] = Field(default_factory=list)
    rules: list[RuleHit] = Field(default_factory=list)
    attack_technique: str | None = None
    explanation: str | None = None
    event_id: str | None = None
    client_transaction_id: str | None = None

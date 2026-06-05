"""Aegis Verdict — the single domain type every surface emits.

The shape locked here flows through:
- S1 middleware (aegis_mw): every tool/subagent/model boundary
- S2 MCP server (aegis_mcp): tool outputSchema is Verdict.model_json_schema()
- S3 DefenseClaw integration: Aegis HTTP sink wraps responses as Verdict
- S4 Splunk app: events land under sourcetype cisco_ai_defense:aegis_verdict

Cross-references:
- docs/architecture.md § "API schemas" → "Verdict (the type every surface emits)"
- ../context/07-cisco-stack/01-ai-defense-deep.md (Severity NONE_SEVERITY,
  rules field name, response shape)
- ../context/10-standards/02-otel-genai-semantic-conventions.md
  (gen_ai.evaluation.result event score.label slot)
- ADR-003: Foundation-Sec is EXPLAINER not classifier; RuleHit.source
  must NEVER include "foundation_sec_classifier"
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """Verdict severity. Mirrors Cisco AI Defense Inspection API response enum.

    Per ../context/07-cisco-stack/01-ai-defense-deep.md, the API includes
    NONE_SEVERITY alongside LOW/MEDIUM/HIGH. Including it here keeps the
    AI Defense client (story-judges-01) round-trip-safe.
    """

    NONE_SEVERITY = "NONE_SEVERITY"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class VerdictLabel(StrEnum):
    """Aegis action verdict. Maps to OTel `gen_ai.evaluation.result.score.label`.

    Lower-cased via `.value.lower()` for the OTel emission.
    """

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    MODIFY = "MODIFY"
    REVIEW = "REVIEW"


class RuleHit(BaseModel):
    """A single rule firing inside a Verdict.

    `source` is intentionally narrow: only the three primary-source-grounded
    classifiers populate it. Foundation-Sec NEVER appears — see ADR-003.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]


class Verdict(BaseModel):
    """The verdict returned by every Aegis surface.

    Every field maps 1:1 to docs/architecture.md § "API schemas" → Verdict.
    Field names (especially `rules`, not `triggered_rules`) match Cisco AI
    Defense's response shape so the AI Defense client can populate directly.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    timestamp: datetime
    verdict: VerdictLabel
    severity: Severity
    rules: list[RuleHit]
    explanation: str | None = None
    classifications: list[str] = Field(default_factory=list)
    modifications: dict[str, object] | None = None
    surface: Literal[
        "mw_model",
        "mw_tool",
        "mw_subagent",
        "mcp_score",
        "mcp_judge_tool",
        "mcp_check_output",
        "mcp_audit",
        "defenseclaw",
    ]
    latency_ms: float
    # agent_id is the logical agent identifier (e.g. splunklib.ai thread_id
    # at the model_middleware integration point). Optional because some
    # surfaces (mcp_audit on a session-less call) genuinely don't know one;
    # downstream ES Risk-Based Alerting (story-app-08) uses agent_id as the
    # _risk_object so populating it is load-bearing for the Splunk surface.
    agent_id: str | None = None


def verdict_to_json_schema() -> dict[str, object]:
    """Return the canonical Verdict JSON Schema (load-bearing for MCP outputSchema)."""
    return Verdict.model_json_schema()

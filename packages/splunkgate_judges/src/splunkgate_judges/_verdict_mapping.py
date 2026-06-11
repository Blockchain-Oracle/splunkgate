"""Canonical mapping from Cisco AI Defense `InspectResponse` → `splunkgate_core.Verdict`.

This is the schema boundary between the upstream AI Defense response and the
domain `Verdict` type emitted by every SplunkGate surface. Keeping it in a
dedicated module makes the mapping rule reviewable in one place and avoids
re-implementing it in each middleware that wraps the client.

Mapping rules (per docs/architecture.md § "API schemas" + docs/PRD.md):

- `is_safe == True`                          → `VerdictLabel.ALLOW`
- `is_safe == False ∧ severity ∈ {LOW, MED}` → `VerdictLabel.REVIEW`
- `is_safe == False ∧ severity == HIGH`      → `VerdictLabel.BLOCK`
- `is_safe == False ∧ severity == NONE`      → `VerdictLabel.REVIEW`
  (degenerate "not safe but no severity" — surface for human review)

- `rules[].rule_name` → `RuleHit.rule` verbatim (one of the 11 canonical names)
- `rules[].classification` ignored at the core layer — the Verdict's
  `classifications` field already carries that taxonomy
- `RuleHit.confidence` is hard-coded to 1.0; Cisco does not return per-rule
  scores, only the binary "fired" signal. Future Foundation-Sec re-scoring
  (EPIC-05) may revise this, but per ADR-003 the rule list comes from AI
  Defense only.
- `RuleHit.source` is locked to `"ai_defense"` — this module is the AI Defense
  boundary by definition.

- `explanation`: Cisco's own explanation pass-through. Foundation-Sec re-
  explanation lives in EPIC-05/06 and is not called here (ADR-003 boundary).
- `classifications`: `Classification` enum values → `list[str]` of their
  string values for downstream SPL queries that need string-typed fields.
- `modifications`: always `None` from this mapping. The AI Defense
  Inspection API doesn't return a modified-payload field; tool-call
  redaction happens further upstream in the middleware layer.
- `agent_id`: not derivable from the InspectResponse alone — passed in by
  the caller as `None` here; the wrapping middleware populates it from
  the request context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from splunkgate_core.verdict import RuleHit, Severity, Verdict, VerdictLabel

if TYPE_CHECKING:
    from uuid import UUID

    from splunkgate_core.verdict import Surface

    from splunkgate_judges.ai_defense_types import InspectResponse


def inspect_response_to_verdict(
    resp: InspectResponse,
    *,
    trace_id: UUID,
    surface: Surface,
    latency_ms: float,
    agent_id: str | None = None,
) -> Verdict:
    """Translate an AI Defense `InspectResponse` into a SplunkGate `Verdict`.

    Pure function — no I/O, no logging. Idempotent on inputs.
    """
    if resp.is_safe:
        label = VerdictLabel.ALLOW
    elif resp.severity is Severity.HIGH:
        label = VerdictLabel.BLOCK
    else:
        # Includes LOW, MEDIUM, and NONE_SEVERITY (the degenerate
        # "not safe but no severity" case surfaces for human review).
        label = VerdictLabel.REVIEW

    rules = [
        RuleHit(
            rule=str(hit.rule_name),
            confidence=1.0,
            source="ai_defense",
        )
        for hit in resp.rules
    ]
    classifications = [str(c) for c in resp.classifications]

    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=label,
        severity=resp.severity,
        rules=rules,
        explanation=resp.explanation,
        classifications=classifications,
        modifications=None,
        surface=surface,
        latency_ms=latency_ms,
        agent_id=agent_id,
    )

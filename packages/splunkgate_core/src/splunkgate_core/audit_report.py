"""AuditReport — aggregate verdict view for story-mcp-05's audit_trace tool.

Per docs/plans/2026-06-09-mcp-design.md § "New backend modules", this is
the shared Pydantic shape that splunkgate_audit_trace returns and that
Surface 4 dashboards deserialize. Lives in splunkgate_core (NOT
splunkgate_mcp) so the dashboard layer can import without coupling to
the MCP package.

NOTE: `aggregate` is `dict[str, object]`, NOT `dict[str, Any]` — CLAUDE.md
hard rule "no Any in splunkgate_core or splunkgate_judges". The freeform
dict mirrors the SPL stats output (e.g. {"BLOCK": 2, "ALLOW": 1} for a
`stats count by verdict`); callers access via repr() / isinstance, same
pattern as Verdict.modifications.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from splunkgate_core.verdict import Surface, Verdict


class AuditReport(BaseModel):
    """Aggregate report over every Verdict emitted for a single trace_id.

    Returned by `splunkgate_audit_trace` (story-mcp-05). Surface 4
    dashboards deserialize this shape to render "the audit trail of
    agent decisions" for the regulator-evidence-pack panel.

    Fields:
      trace_id: the queried trace identifier
      event_count: total events found (== len(verdicts))
      verdicts: every Verdict object reconstructed from the SPL rows
      first_seen / last_seen: timestamp envelope; None when event_count == 0
      surfaces_seen: deduped union of `Verdict.surface` values across the
        returned verdicts (typed against the same Literal so mypy catches
        any surface drift between this aggregate and the Verdict shape)
      aggregate: freeform `stats count by ...` output keyed by the
        eval_dimensions tuple; `dict[str, object]` per CLAUDE.md
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: UUID
    event_count: int
    verdicts: list[Verdict]
    first_seen: datetime | None
    last_seen: datetime | None
    surfaces_seen: list[Surface]
    aggregate: dict[str, object]


def audit_report_to_json_schema() -> dict[str, object]:
    """Return the canonical AuditReport JSON Schema (MCP outputSchema)."""
    return AuditReport.model_json_schema()

"""MCP tool `splunkgate_audit_trace` (story-mcp-05, Surface 2).

Aggregates every SplunkGate verdict event for a given trace_id by
querying Splunk REST `/services/search/jobs` for events under
`sourcetype=cisco_ai_defense:splunkgate_verdict`. Returns a typed
`AuditReport` — the ONLY MCP tool whose `outputSchema` is the
AuditReport JSON schema rather than the Verdict schema.

SPL injection guard: `eval_dimensions` is an allowlist parameter
(spec line 149). Anything outside the allowlist raises
`ValidationError` BEFORE the REST call is issued.

Per MCP spec, errors surface in-band via `isError: true` — we raise
`SplunkSearchError` / `ValidationError` and FastMCP converts. Empty
result is NOT an error: returns AuditReport with event_count == 0.
The OTel `gen_ai.evaluation.result` event carries the custom
`splunkgate.audit.event_count` attribute per story spec line 73.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Final, Literal, get_args
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from splunkgate_core.audit_report import AuditReport
from splunkgate_core.errors import ValidationError
from splunkgate_core.otel import AttrValue, emit_verdict_event
from splunkgate_core.verdict import (
    RuleHit,
    Severity,
    Surface,
    Verdict,
    VerdictLabel,
)
from splunkgate_judges.splunk_search import SplunkSearchClient

_LOGGER = logging.getLogger(__name__)

# Locked literals — Surface 4 dashboards filter on these strings.
_SURFACE: Literal["mcp_audit"] = "mcp_audit"
_MCP_METHOD: str = "tools/call"

# Sourcetype per ADR-005. Verified live on Abu's Splunk Cloud instance.
_SOURCETYPE: Final[str] = "cisco_ai_defense:splunkgate_verdict"

# Default index — agents typically write to `main`. Configurable later
# via an env var if a sourcetype-router rerouting story lands.
_INDEX: Final[str] = "main"

# Allowlist for SPL-safe stats dimensions (spec line 149). Anything
# outside this set is rejected by `_validate_dimensions` before we
# interpolate anything into the SPL string.
_ALLOWED_DIMENSIONS: Final[frozenset[str]] = frozenset(
    {
        "verdict",
        "severity",
        "surface",
        "rules",
        "classifications",
        "tool_name",
        "agent_id",
    }
)

# Default eval dimensions if caller doesn't pass any. Order is locked
# because Surface 4 dashboards index into the aggregate dict by the
# verbatim dimension tuple.
_DEFAULT_DIMENSIONS: Final[list[str]] = ["verdict", "severity", "surface"]

# Default search window. 7 days is the maximum the regulator-evidence
# pack panel reads; longer ranges require a future story for KV-store
# pagination per ADR-013.
_DEFAULT_EARLIEST: Final[str] = "-7d"
_DEFAULT_LATEST: Final[str] = "now"

# Valid Surface literal values used to narrow rows from Splunk back into
# our `Surface` Literal type. Derived from the Literal so adding a
# surface in verdict.py automatically widens this set.
_VALID_SURFACES: Final[frozenset[str]] = frozenset(get_args(Surface))


class AuditTraceInputs(BaseModel):
    """Input arguments for `splunkgate_audit_trace`.

    `trace_id` is the canonical UUID the agent recorded at its origin
    surface (typically the W3C trace-context root). `eval_dimensions`
    selects the `stats count by ...` slice; values MUST be in the
    locked allowlist or the tool raises `ValidationError` BEFORE
    issuing the Splunk REST call.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    eval_dimensions: list[str] = Field(default_factory=lambda: list(_DEFAULT_DIMENSIONS))


def _validate_dimensions(dimensions: list[str]) -> list[str]:
    """Reject dimensions outside the allowlist; return them verbatim.

    Spec line 149: SPL injection guard. The caller-supplied list is the
    ONLY user-controlled input that touches the SPL string. We compare
    each entry against `_ALLOWED_DIMENSIONS` and refuse anything else.
    This MUST run BEFORE the REST call, so respx call_count == 0 on
    rejected input (BDD criterion 9).
    """
    if not dimensions:
        msg = "eval_dimensions must contain at least one field"
        raise ValidationError(msg)
    bad = [d for d in dimensions if d not in _ALLOWED_DIMENSIONS]
    if bad:
        allowed_sorted = sorted(_ALLOWED_DIMENSIONS)
        msg = f"eval_dimensions contains disallowed entries {bad!r}; allowed: {allowed_sorted}"
        raise ValidationError(msg)
    return dimensions


def _build_spl(trace_id: UUID, dimensions: list[str]) -> str:
    """Compose the SPL search string.

    Pattern: `search index=<idx> sourcetype=<st> trace_id=<uuid> | stats count by <dims>`.
    The dimensions list is allowlist-validated by `_validate_dimensions`
    BEFORE this function runs, so direct interpolation is SPL-safe.
    UUIDs are RFC-4122-shaped (hex + hyphens), so direct interpolation
    of `trace_id` is also safe.
    """
    by_clause = ",".join(dimensions)
    return (
        f"search index={_INDEX} sourcetype={_SOURCETYPE} "
        f"trace_id={trace_id} | stats count by {by_clause}"
    )


def _coerce_timestamp(value: object) -> datetime | None:
    """Best-effort parse of a Splunk `_time` field; None on parse failure."""
    if isinstance(value, str):
        try:
            # Python 3.11+ fromisoformat() handles trailing "Z" natively.
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value
    return None


def _coerce_uuid(value: object, fallback: UUID) -> UUID:
    """Parse a string UUID; fall back to the caller's queried trace_id."""
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return fallback
    return fallback


def _coerce_label(value: object) -> VerdictLabel:
    """Map a string row field to VerdictLabel; default ALLOW + WARN on miss.

    Per PR #119 silent-failure-hunter + code-reviewer #2: an unrecognized
    verdict string (schema drift, future label, casing typo) was silently
    downgraded to ALLOW. Regulator-evidence-pack dashboards would show a
    falsified verdict. Log so the coercion miss is visible.
    """
    if isinstance(value, str):
        try:
            return VerdictLabel(value.upper())
        except ValueError:
            _LOGGER.warning(
                "audit_trace.coerce_miss",
                extra={"field": "verdict", "value": value, "fallback": "ALLOW"},
            )
            return VerdictLabel.ALLOW
    if value is not None:
        _LOGGER.warning(
            "audit_trace.coerce_miss",
            extra={"field": "verdict", "value": repr(value), "fallback": "ALLOW"},
        )
    return VerdictLabel.ALLOW


def _coerce_severity(value: object) -> Severity:
    """Map a string row to Severity; default NONE_SEVERITY + WARN on miss."""
    if isinstance(value, str):
        try:
            return Severity(value.upper())
        except ValueError:
            _LOGGER.warning(
                "audit_trace.coerce_miss",
                extra={"field": "severity", "value": value, "fallback": "NONE_SEVERITY"},
            )
            return Severity.NONE_SEVERITY
    if value is not None:
        _LOGGER.warning(
            "audit_trace.coerce_miss",
            extra={"field": "severity", "value": repr(value), "fallback": "NONE_SEVERITY"},
        )
    return Severity.NONE_SEVERITY


def _coerce_surface(value: object) -> Surface:
    """Map a string row to Surface; default `mcp_audit` + WARN on miss."""
    if isinstance(value, str) and value in _VALID_SURFACES:
        # Membership test makes the cast to Surface (Literal) safe.
        return value  # type: ignore[return-value]
    if value is not None:
        _LOGGER.warning(
            "audit_trace.coerce_miss",
            extra={"field": "surface", "value": repr(value), "fallback": _SURFACE},
        )
    return _SURFACE


def _row_to_verdict(row: dict[str, object], fallback_trace_id: UUID) -> Verdict:
    """Reconstruct a Verdict from one SPL result row.

    Splunk-indexed events don't carry the original AI Defense confidence
    or its `RuleHit.source`. We default to confidence=1.0 + source=
    "ai_defense" — the dominant emit path; tolerate missing fields so
    aggregation never crashes on a partially-indexed row.
    """
    raw_rules = row.get("rules", [])
    rule_hits: list[RuleHit] = []
    if isinstance(raw_rules, list):
        rule_hits.extend(
            RuleHit(rule=r, confidence=1.0, source="ai_defense")
            for r in raw_rules
            if isinstance(r, str)
        )
    classifications_raw = row.get("classifications", [])
    classifications: list[str] = (
        [c for c in classifications_raw if isinstance(c, str)]
        if isinstance(classifications_raw, list)
        else []
    )
    explanation_raw = row.get("explanation")
    explanation = explanation_raw if isinstance(explanation_raw, str) else None
    latency_raw = row.get("latency_ms", 0.0)
    latency_ms = (
        float(latency_raw)
        if isinstance(latency_raw, (int, float)) and not isinstance(latency_raw, bool)
        else 0.0
    )
    timestamp = _coerce_timestamp(row.get("_time")) or datetime.now(UTC)
    agent_id_raw = row.get("agent_id")
    agent_id = agent_id_raw if isinstance(agent_id_raw, str) else None
    return Verdict(
        trace_id=_coerce_uuid(row.get("trace_id"), fallback_trace_id),
        timestamp=timestamp,
        verdict=_coerce_label(row.get("verdict")),
        severity=_coerce_severity(row.get("severity")),
        rules=rule_hits,
        explanation=explanation,
        classifications=classifications,
        surface=_coerce_surface(row.get("surface")),
        latency_ms=latency_ms,
        agent_id=agent_id,
    )


def _build_aggregate(
    rows: list[dict[str, object]],
    dimensions: list[str],
) -> dict[str, object]:
    """Project rows into the aggregate dict keyed by dimension-tuple.

    Single dim ["verdict"] → keys like "BLOCK", "ALLOW". Multi dim
    ["verdict","severity"] → keys like "BLOCK|HIGH". Sums on collision.
    """
    aggregate: dict[str, object] = {}
    for row in rows:
        key_parts: list[str] = []
        for dim in dimensions:
            raw = row.get(dim)
            key_parts.append(str(raw) if raw is not None else "")
        key = "|".join(key_parts)
        count_raw = row.get("count", 0)
        # `count_raw` is typed `object` (Splunk row values are heterogeneous).
        # Narrow to types `int()` accepts before calling — mypy rejects `int(object)`.
        if isinstance(count_raw, bool):
            count = 0  # ignore bools (`True` would coerce to 1, misleading)
        elif isinstance(count_raw, (int, str)):
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                count = 0
        else:
            count = 0
        existing = aggregate.get(key)
        if isinstance(existing, int):
            aggregate[key] = existing + count
        else:
            aggregate[key] = count
    return aggregate


def _build_audit_report(
    *,
    rows: list[dict[str, object]],
    trace_id: UUID,
    dimensions: list[str],
) -> AuditReport:
    """Assemble AuditReport from rows. Empty result → event_count == 0."""
    verdicts = [_row_to_verdict(row, trace_id) for row in rows]
    timestamps = [v.timestamp for v in verdicts]
    first_seen = min(timestamps) if timestamps else None
    last_seen = max(timestamps) if timestamps else None
    # Dedup surfaces preserving first-seen order for deterministic rendering.
    seen: set[str] = set()
    surfaces_ordered: list[Surface] = []
    for v in verdicts:
        if v.surface not in seen:
            seen.add(v.surface)
            surfaces_ordered.append(v.surface)
    return AuditReport(
        trace_id=trace_id,
        event_count=len(verdicts),
        verdicts=verdicts,
        first_seen=first_seen,
        last_seen=last_seen,
        surfaces_seen=surfaces_ordered,
        aggregate=_build_aggregate(rows, dimensions),
    )


def _aggregate_verdict_for_otel(
    *,
    report: AuditReport,
    trace_id: UUID,
    started: float,
) -> Verdict:
    """Synthesize a Verdict wrapper (surface=mcp_audit, ALLOW) for OTel emit."""
    return Verdict(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation=f"audit_trace returned {report.event_count} events",
        surface=_SURFACE,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _safe_emit(verdict: Verdict, event_count: int) -> None:
    """Emit OTel event with `splunkgate.audit.event_count`; observability-safe.

    Per silent-failure-hunter on PR #116/#117/#118: exporter crash must
    not propagate out of the tool. Catch broadly, log, continue.
    """
    extras: dict[str, AttrValue] = {"splunkgate.audit.event_count": event_count}
    try:
        emit_verdict_event(verdict, mcp_method_name=_MCP_METHOD, extra_attributes=extras)
    except Exception:  # noqa: BLE001 — observability must never lose the verdict
        _LOGGER.warning(
            "otel.emit_failed",
            extra={"trace_id": str(verdict.trace_id), "surface": verdict.surface},
            exc_info=True,
        )


async def audit_trace(args: AuditTraceInputs) -> AuditReport:
    """Aggregate every SplunkGate verdict for a trace_id; return AuditReport.

    Logic:
      1. Allowlist-validate eval_dimensions → ValidationError BEFORE REST.
      2. Compose SPL (trace_id + dimensions are the only interpolations).
      3. Submit search; non-2xx → SplunkSearchError (FastMCP → isError).
      4. Build AuditReport. Empty result returns event_count=0 (NOT error).
      5. Emit OTel `gen_ai.evaluation.result` w/ surface=mcp_audit +
         `splunkgate.audit.event_count` attribute.
    """
    started = time.perf_counter()
    dimensions = _validate_dimensions(args.eval_dimensions)
    spl = _build_spl(args.trace_id, dimensions)
    async with await SplunkSearchClient.from_env() as client:
        rows = await client.submit_search(
            spl,
            earliest=_DEFAULT_EARLIEST,
            latest=_DEFAULT_LATEST,
        )
    report = _build_audit_report(rows=rows, trace_id=args.trace_id, dimensions=dimensions)
    wrapper = _aggregate_verdict_for_otel(report=report, trace_id=uuid4(), started=started)
    _safe_emit(wrapper, event_count=report.event_count)
    return report


def register(server_module: object) -> None:
    """Register this tool on the SplunkGate MCP server's registry."""
    register_tool = server_module.register_tool  # type: ignore[attr-defined]
    register_tool(
        name="splunkgate_audit_trace",
        fn=audit_trace,
        description=(
            "Aggregate every SplunkGate verdict for a given trace_id. Queries "
            "Splunk REST `/services/search/jobs` for `cisco_ai_defense:"
            "splunkgate_verdict` events, runs a `stats count by <eval_dimensions>` "
            "projection (allowlist-validated to prevent SPL injection), and "
            "returns a typed AuditReport. Surface='mcp_audit'."
        ),
    )

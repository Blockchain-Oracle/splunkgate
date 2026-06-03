"""Aegis core domain types: Verdict, Severity, OTel emission, error model."""

from aegis_core.errors import (
    AegisError,
    ConfigError,
    JudgmentError,
    NetworkError,
)
from aegis_core.otel import emit_verdict_event, severity_to_score
from aegis_core.trace import (
    current_trace_id,
    new_trace_id,
    set_trace_id,
    trace_context,
)
from aegis_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
    verdict_to_json_schema,
)
from aegis_core.verdict_context import VerdictContext

__version__ = "0.0.1"
__all__: list[str] = [
    "AegisError",
    "ConfigError",
    "JudgmentError",
    "NetworkError",
    "RuleHit",
    "Severity",
    "Verdict",
    "VerdictContext",
    "VerdictLabel",
    "current_trace_id",
    "emit_verdict_event",
    "new_trace_id",
    "set_trace_id",
    "severity_to_score",
    "trace_context",
    "verdict_to_json_schema",
]

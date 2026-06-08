"""SplunkGate core domain types: Verdict, Severity, OTel emission, error model, logging."""

from splunkgate_core.errors import (
    ConfigError,
    JudgmentError,
    ModelInputBlockedBySplunkGate,
    ModelOutputBlockedBySplunkGate,
    NetworkError,
    SplunkGateError,
)
from splunkgate_core.logging import configure_logging, get_logger
from splunkgate_core.otel import emit_verdict_event, severity_to_score
from splunkgate_core.otel_hec_exporter import (
    SplunkHECExporter,
    configure_hec_exporter,
    shutdown_hec_exporter,
)
from splunkgate_core.trace import (
    current_trace_id,
    new_trace_id,
    set_trace_id,
    trace_context,
)
from splunkgate_core.verdict import (
    RuleHit,
    Severity,
    Verdict,
    VerdictLabel,
    verdict_to_json_schema,
)
from splunkgate_core.verdict_context import VerdictContext

__version__ = "0.0.1"
__all__: list[str] = [
    "ConfigError",
    "JudgmentError",
    "ModelInputBlockedBySplunkGate",
    "ModelOutputBlockedBySplunkGate",
    "NetworkError",
    "RuleHit",
    "Severity",
    "SplunkGateError",
    "SplunkHECExporter",
    "Verdict",
    "VerdictContext",
    "VerdictLabel",
    "configure_hec_exporter",
    "configure_logging",
    "current_trace_id",
    "emit_verdict_event",
    "get_logger",
    "new_trace_id",
    "set_trace_id",
    "severity_to_score",
    "shutdown_hec_exporter",
    "trace_context",
    "verdict_to_json_schema",
]

"""Aegis core domain types: Verdict, Severity, OTel emission, error model."""

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
    "RuleHit",
    "Severity",
    "Verdict",
    "VerdictContext",
    "VerdictLabel",
    "verdict_to_json_schema",
]

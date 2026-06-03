"""Aegis multi-judge layer: AI Defense client, DefenseClaw shim, Foundation-Sec explainer."""

from aegis_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    EnabledRule,
    InspectConfig,
    InspectMessage,
    InspectRequest,
    InspectResponse,
    RuleHit,
)

__version__ = "0.1.0"
__all__: list[str] = [
    "AIDefenseRule",
    "Classification",
    "EnabledRule",
    "InspectConfig",
    "InspectMessage",
    "InspectRequest",
    "InspectResponse",
    "RuleHit",
]

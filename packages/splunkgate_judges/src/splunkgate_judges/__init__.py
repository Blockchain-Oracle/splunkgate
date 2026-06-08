"""SplunkGate multi-judge layer: AI Defense client, DefenseClaw shim, template verdict explainer."""

from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    EnabledRule,
    InspectConfig,
    InspectMessage,
    InspectRequest,
    InspectResponse,
    RuleHit,
)
from splunkgate_judges.explainer import explain_verdict

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
    "explain_verdict",
]

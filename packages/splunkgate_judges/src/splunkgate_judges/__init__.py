"""SplunkGate multi-judge layer: AI Defense client, DefenseClaw shim, template verdict explainer, Foundation-Sec `| ai` SPL explainer."""

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
from splunkgate_judges.foundsec_spl import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MOCK_ENV_VAR,
    build_ai_spl,
    explain_via_ai_spl,
)

__version__ = "0.1.0"
__all__: list[str] = [
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "MOCK_ENV_VAR",
    "AIDefenseRule",
    "Classification",
    "EnabledRule",
    "InspectConfig",
    "InspectMessage",
    "InspectRequest",
    "InspectResponse",
    "RuleHit",
    "build_ai_spl",
    "explain_verdict",
    "explain_via_ai_spl",
]

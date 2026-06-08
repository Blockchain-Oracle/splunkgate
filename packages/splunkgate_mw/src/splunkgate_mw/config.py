"""SplunkGate middleware config — frozen pydantic model.

Per architecture.md § "API schemas" → Config, the five fields locked here
are read by every Surface 1 middleware before any AI Defense / DefenseClaw
call. Fields default to safe-for-demo values; production deployments must
set `ai_defense_api_key` via env var or kwarg.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

__all__ = ["Config"]


class Config(BaseModel):
    """Frozen configuration for every SplunkGate middleware class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ai_defense_endpoint: str = Field(
        default="https://us.api.inspect.aidefense.security.cisco.com",
        description="Cisco AI Defense Inspection API regional endpoint.",
    )
    ai_defense_api_key: SecretStr | None = Field(
        default=None,
        description="Cisco AI Defense API key. None when SPLUNKGATE_AI_DEFENSE_MOCK=1.",
    )
    foundation_sec_enabled: bool = Field(
        default=True,
        description="Whether to call the Foundation-Sec explainer via | ai SPL.",
    )
    escalate_on_first_pass_hit: bool = Field(
        default=True,
        description="If splunklib.security first-pass flags risk, skip AI Defense call.",
    )
    splunklib_security_first_pass: bool = Field(
        default=True,
        description="Whether to run splunklib.security as the cheap first-pass scan.",
    )

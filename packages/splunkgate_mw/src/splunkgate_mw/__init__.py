"""SplunkGate middleware library for splunklib.ai (Surface 1)."""

from splunkgate_mw._base import (
    SafetyAgentMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from splunkgate_mw.config import Config
from splunkgate_mw.model_middleware import SafetyModelMiddleware
from splunkgate_mw.profiles import (
    DEFAULT_PROFILE,
    FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE,
    PUBLIC_SECTOR_PROFILE,
    Profile,
    resolve_profile,
)

__version__ = "0.1.0"
__all__ = [
    "DEFAULT_PROFILE",
    "FINANCIAL_SERVICES_PROFILE",
    "HEALTHCARE_PROFILE",
    "PUBLIC_SECTOR_PROFILE",
    "Config",
    "Profile",
    "SafetyAgentMiddleware",
    "SafetyModelMiddleware",
    "SafetySubagentMiddleware",
    "SafetyToolMiddleware",
    "resolve_profile",
]

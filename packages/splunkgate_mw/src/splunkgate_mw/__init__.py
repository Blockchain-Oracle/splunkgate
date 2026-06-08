"""SplunkGate middleware library for splunklib.ai (Surface 1)."""

from splunkgate_mw._base import (
    SafetyAgentMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from splunkgate_mw.config import Config
from splunkgate_mw.model_middleware import SafetyModelMiddleware
from splunkgate_mw.profiles import Profile

__version__ = "0.1.0"
__all__ = [
    "Config",
    "Profile",
    "SafetyAgentMiddleware",
    "SafetyModelMiddleware",
    "SafetySubagentMiddleware",
    "SafetyToolMiddleware",
]

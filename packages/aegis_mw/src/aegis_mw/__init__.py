"""Aegis middleware library for splunklib.ai (Surface 1)."""

from aegis_mw._base import (
    SafetyAgentMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyToolMiddleware,
)
from aegis_mw.config import Config
from aegis_mw.profiles import DEFAULT_PROFILE, Profile

__version__ = "0.1.0"
__all__ = [
    "DEFAULT_PROFILE",
    "Config",
    "Profile",
    "SafetyAgentMiddleware",
    "SafetyModelMiddleware",
    "SafetySubagentMiddleware",
    "SafetyToolMiddleware",
]

"""AI Defense-scoped error subclasses under SplunkGateError."""

from splunkgate_core.errors import SplunkGateError


class AIDefenseError(SplunkGateError):
    """Base for every AI Defense client error."""


class AIDefenseAuthError(AIDefenseError):
    """HTTP 401/403 — bad API key or missing entitlement. Non-retryable."""


class AIDefenseTimeoutError(AIDefenseError):
    """httpx timeout — wraps httpx.TimeoutException as a domain error."""


class AIDefenseUpstreamError(AIDefenseError):
    """HTTP 5xx — Cisco-side failure. Retryable."""

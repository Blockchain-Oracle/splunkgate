"""AI Defense-scoped error subclasses under AegisError."""

from aegis_core.errors import AegisError


class AIDefenseError(AegisError):
    """Base for every AI Defense client error."""


class AIDefenseAuthError(AIDefenseError):
    """HTTP 401/403 — bad API key or missing entitlement. Non-retryable."""


class AIDefenseTimeoutError(AIDefenseError):
    """httpx timeout — wraps httpx.TimeoutException as a domain error."""


class AIDefenseUpstreamError(AIDefenseError):
    """HTTP 5xx — Cisco-side failure. Retryable."""

"""Judge-scoped error subclasses under SplunkGateError."""

from splunkgate_core.errors import SplunkGateError


class AIDefenseError(SplunkGateError):
    """Base for every AI Defense client error."""


class AIDefenseAuthError(AIDefenseError):
    """HTTP 401/403 — bad API key or missing entitlement. Non-retryable."""


class AIDefenseTimeoutError(AIDefenseError):
    """httpx timeout — wraps httpx.TimeoutException as a domain error."""


class AIDefenseUpstreamError(AIDefenseError):
    """HTTP 5xx — Cisco-side failure. Retryable."""


class SplunkSearchError(SplunkGateError):
    """Splunk REST `/services/search/jobs` failure.

    Raised by `splunkgate_judges.splunk_search.SplunkSearchClient` on any
    non-2xx response from the Splunk REST search endpoint, including
    auth failures, malformed SPL responses, and 5xx upstream errors.
    Mapped to MCP in-band `isError: true` by FastMCP's lowlevel
    `CallToolRequest` handler per the MCP spec.
    """

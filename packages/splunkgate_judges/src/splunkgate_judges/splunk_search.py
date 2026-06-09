"""Splunk REST search client — generic search abstraction.

Per docs/plans/2026-06-09-mcp-design.md, this module is generically
useful: story-mcp-05 audit_trace consumes it now; future foundsec-02
(when undeferred) can reuse for its `| ai` SPL execution path. Lives
in splunkgate_judges, NOT under foundation_sec (which is DEFERRED).

Auth: USER + PASSWORD basic auth via env vars
(SPLUNKGATE_SPLUNK_HOST, SPLUNKGATE_SPLUNK_USER,
SPLUNKGATE_SPLUNK_PASSWORD). HEC token is write-only — wrong scope
for `/services/search/jobs`.

TLS: defaults to verify=True. SPLUNKGATE_DEV_INSECURE_TLS=1 opts in
to insecure mode (self-signed certs for local Docker dev). Mirrors
the pattern in splunkgate_core/otel_hec_exporter.py:198, including
the WARN log so the escape hatch is visible in dashboards.

Honest typing: SPL payload + result rows are `dict[str, object]`
(NOT `Any`) per CLAUDE.md "no Any in splunkgate_core or
splunkgate_judges". Callers narrow via `isinstance` at use sites.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Self

import httpx
from splunkgate_core.errors import ConfigError

from splunkgate_judges._errors import SplunkSearchError

if TYPE_CHECKING:
    from types import TracebackType

_LOGGER = logging.getLogger(__name__)

# Env-var keys — copied to module constants so a typo surfaces at import.
_ENV_HOST = "SPLUNKGATE_SPLUNK_HOST"
_ENV_USER = "SPLUNKGATE_SPLUNK_USER"
_ENV_PASSWORD = "SPLUNKGATE_SPLUNK_PASSWORD"  # noqa: S105 — env var name, not a secret  # nosec B105
_ENV_INSECURE_TLS = "SPLUNKGATE_DEV_INSECURE_TLS"

# Splunk REST endpoint path for the synchronous oneshot search.
_SEARCH_JOBS_PATH = "/services/search/jobs"

# Truthy values for the insecure-TLS opt-in — same set used by
# `splunkgate_judges.foundsec_spl._TRUTHY`. Case-insensitive comparison.
_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})

# Connection timeout — keeps the Splunk search call from hanging the MCP
# tool indefinitely. 30s matches the AI Defense client default budget.
_DEFAULT_TIMEOUT_S = 30.0

# HTTP success range used by Splunk REST: 2xx means the search job was
# accepted and (in oneshot mode) returned its results. Anything else
# raises `SplunkSearchError`.
_HTTP_2XX_FLOOR = 200
_HTTP_3XX_FLOOR = 300


def _truthy_env(key: str) -> bool:
    """Return True if env var `key` is set to a truthy literal."""
    raw = os.environ.get(key, "").strip().lower()
    return raw in _TRUTHY


def _require_env(key: str) -> str:
    """Read env var `key`; raise ConfigError if missing/empty."""
    value = os.environ.get(key, "").strip()
    if not value:
        msg = f"{key} not set (or empty); required for Splunk REST search"
        raise ConfigError(msg)
    return value


def _check_splunk_messages(parsed: dict[str, object]) -> None:
    """Raise `SplunkSearchError` if Splunk's response carries FATAL/ERROR.

    Extracted out of `submit_search` to keep cyclomatic complexity down
    (ruff C901) — the FATAL-detection branch was added in PR #119 review
    to close the silent-failure-hunter finding where a Splunk 200 with
    a malformed-SPL FATAL body was treated as empty success.
    """
    messages = parsed.get("messages")
    if not isinstance(messages, list):
        return
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        msg_type = entry.get("type")
        if not isinstance(msg_type, str):
            continue
        if msg_type.upper() not in {"FATAL", "ERROR"}:
            continue
        text = entry.get("text", "<no message>")
        msg = f"Splunk REST returned {msg_type} message: {text!r}"
        raise SplunkSearchError(msg)


class SplunkSearchClient:
    """Async Splunk REST `/services/search/jobs` client.

    Owns its own `httpx.AsyncClient` instance constructed in `from_env`.
    Callers MUST call `aclose()` to release the connection pool, or use
    `async with SplunkSearchClient.from_env() as client:` per the
    recommended pattern in the design doc.

    Disambiguation: the consumer-facing API is `submit_search(spl, ...)`
    which runs a oneshot synchronous search and returns the parsed
    results list. We do NOT expose lower-level job-lifecycle helpers in
    v1 — extend if a downstream story needs async polling.
    """

    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        verify: bool = True,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        """Build a client around an httpx.AsyncClient with basic auth + TLS.

        Args:
            host: Splunk REST base URL (e.g. https://splunk.example:8089).
            user: REST user (typically sc_admin in Splunk Cloud).
            password: REST password.
            verify: TLS verification. Default True; pass False only when
                `SPLUNKGATE_DEV_INSECURE_TLS=1` opts in (see from_env).
            timeout: per-request timeout in seconds.
        """
        self._host = host.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._host,
            auth=httpx.BasicAuth(user, password),
            verify=verify,
            timeout=timeout,
        )

    @classmethod
    async def from_env(cls) -> Self:
        """Construct a client from the SPLUNKGATE_SPLUNK_* env vars.

        Reads `SPLUNKGATE_SPLUNK_HOST`, `SPLUNKGATE_SPLUNK_USER`, and
        `SPLUNKGATE_SPLUNK_PASSWORD`. Honors `SPLUNKGATE_DEV_INSECURE_TLS=1`
        as a documented opt-in for self-signed certs (local Docker
        Splunk) with a WARN log so the escape hatch is visible in
        Splunk dashboards instead of silently shipping `verify=False`.

        Raises ConfigError when any required env var is missing.
        """
        host = _require_env(_ENV_HOST)
        user = _require_env(_ENV_USER)
        password = _require_env(_ENV_PASSWORD)
        insecure = _truthy_env(_ENV_INSECURE_TLS)
        if insecure:
            _LOGGER.warning(
                "splunk_search.tls_verify_disabled",
                extra={
                    "issue": f"{_ENV_INSECURE_TLS}=1 is set",
                    "resolution": (
                        "production deployments must unset this env var "
                        "and provide a valid TLS chain"
                    ),
                },
            )
        return cls(host=host, user=user, password=password, verify=not insecure)

    async def submit_search(
        self,
        spl: str,
        *,
        earliest: str = "-7d",
        latest: str = "now",
    ) -> list[dict[str, object]]:
        """Run a synchronous oneshot SPL search; return the parsed results.

        Posts to `/services/search/jobs` with `exec_mode=oneshot` and
        `output_mode=json`. The `search` form parameter MUST include the
        leading `search` keyword per Splunk REST docs; callers pass the
        full SPL including the leading verb (e.g. `search index=main ...`).

        Args:
            spl: the SPL command string verbatim.
            earliest: search time range lower bound (Splunk relative time
                or epoch; default `-7d`).
            latest: search time range upper bound (default `now`).

        Returns:
            List of result rows, each a `dict[str, object]` as parsed
            from Splunk's JSON `results` array.

        Raises:
            SplunkSearchError: on any non-2xx response, malformed body,
                or transport-level failure.
        """
        payload: dict[str, str] = {
            "search": spl,
            "exec_mode": "oneshot",
            "output_mode": "json",
            "earliest_time": earliest,
            "latest_time": latest,
        }
        try:
            response = await self._client.post(_SEARCH_JOBS_PATH, data=payload)
        except httpx.HTTPError as exc:
            msg = f"Splunk REST search transport error: {exc!r}"
            raise SplunkSearchError(msg) from exc

        if not (_HTTP_2XX_FLOOR <= response.status_code < _HTTP_3XX_FLOOR):
            # Body may contain Splunk's diagnostic XML — surface it but
            # cap length so a giant error page doesn't flood the log line.
            body_preview = response.text[:500]
            msg = (
                f"Splunk REST returned {response.status_code} for "
                f"{_SEARCH_JOBS_PATH}: {body_preview}"
            )
            _LOGGER.warning(
                "splunk_search.non_2xx",
                extra={
                    "status_code": response.status_code,
                    "body_preview": body_preview,
                },
            )
            raise SplunkSearchError(msg)

        try:
            parsed = response.json()
        except ValueError as exc:
            msg = f"Splunk REST returned non-JSON body: {response.text[:200]!r}"
            raise SplunkSearchError(msg) from exc

        if not isinstance(parsed, dict):
            msg = f"Splunk REST JSON body was not an object: {type(parsed).__name__}"
            raise SplunkSearchError(msg)

        # Splunk sometimes returns HTTP 200 with a FATAL message in the body
        # for malformed SPL — must inspect `messages[].type`. Per PR #119
        # silent-failure-hunter: previously masked SPL errors as empty success.
        _check_splunk_messages(parsed)

        results = parsed.get("results", [])
        if not isinstance(results, list):
            msg = f"Splunk REST `results` field was not a list: {type(results).__name__}"
            raise SplunkSearchError(msg)
        # Narrow each row to dict[str, object] — Splunk may emit list
        # entries that are non-dict (rare, but possible for `| streamstats`
        # edge cases). Drop them with a WARN so we don't crash but the
        # gap is visible.
        rows: list[dict[str, object]] = []
        for idx, row in enumerate(results):
            if isinstance(row, dict):
                # Splunk JSON results are always str-keyed; tighten the
                # inner key-type guarantee for downstream narrowing.
                rows.append({str(k): v for k, v in row.items()})
            else:
                _LOGGER.warning(
                    "splunk_search.non_dict_row",
                    extra={"row_index": idx, "row_type": type(row).__name__},
                )
        return rows

    async def aclose(self) -> None:
        """Release the underlying httpx connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Allow `async with SplunkSearchClient(...) as client:`."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Auto-close on context-manager exit."""
        await self.aclose()

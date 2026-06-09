"""SplunkGate MCP server bootstrap on the official `mcp` Python SDK.

Per docs/architecture.md ADR-004 + ADR-004a, SplunkGate runs its OWN
MCP server alongside Splunk MCP Server (Splunkbase app 7931) and SAIA
(app 7245). The three prefixes (`splunk_*`, `saia_*`, `splunkgate_*`)
partition cleanly in any multi-server MCP client config.

This module owns:
- The `FastMCP` server instance (the SDK boundary)
- A `register_tool(name, fn, description)` helper that (a) wires the tool
  into FastMCP and (b) mirrors the wire-emitted schemas in our internal
  `_REGISTERED_TOOLS` dict by reading them back from FastMCP's tool
  manager after `add_tool` runs (single source of truth)
- `_REGISTERED_TOOLS: dict[str, RegisteredTool]` — the registry that
  tests enumerate via `splunkgate_mcp._test_helpers.list_tools_for_test`
  (FastMCP's async protocol surface is not a sync registry)

Tool registration happens at module import time so `tools/list` works
immediately when the server boots. The `_ping` no-op tool (Task 6) is
registered unconditionally for skeleton-level tests + Splunk-app
dashboard heartbeat. Transport resolution + entry points + Origin check
land in Tasks 7-9.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from splunkgate_core.errors import ConfigError
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.requests import Request

# FastMCP instance — the SDK boundary. Name is the canonical server name
# advertised over the MCP protocol's `initialize` handshake.
server: FastMCP = FastMCP("splunkgate-mcp")


# A tool function: FastMCP introspects the actual signature to derive
# inputSchema (from parameter types — typically a single Pydantic model)
# and outputSchema (from return type — must be a BaseModel / TypedDict /
# dataclass for outputSchema to be populated; otherwise wire emits None).
# Downstream tool stories (mcp-02..05) all use typed Pydantic signatures
# per their story specs, so FastMCP derives the correct schemas.
ToolFn = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Source-of-truth record for a registered MCP tool.

    All schema fields are populated from FastMCP's `_tool_manager` AFTER
    `server.add_tool` runs — so `RegisteredTool.outputSchema` reflects
    what MCP clients actually see on the wire, NOT what we hoped to
    declare. This makes tests that assert
    `RegisteredTool.outputSchema == VERDICT_OUTPUT_SCHEMA` a real
    wire-protocol contract check, not a duplicate-bookkeeping check.

    Tests enumerate these via `_test_helpers.list_tools_for_test()` because
    FastMCP's `list_tools()` is exposed via the async `tools/list` method,
    not as a sync registry call.

    Attribute name `outputSchema` (camelCase) deliberately mirrors the
    MCP wire-protocol field name.
    """

    name: str
    fn: ToolFn
    input_schema: dict[str, Any]
    outputSchema: dict[str, Any] | None  # noqa: N815 — mirrors MCP wire field
    description: str


# The registry. Tests read this via _test_helpers; production uses FastMCP's
# protocol surface directly. Both end up pointing at the same source of
# truth (FastMCP's `_tool_manager._tools[name]`).
_REGISTERED_TOOLS: dict[str, RegisteredTool] = {}


def register_tool(
    *,
    name: str,
    fn: ToolFn,
    description: str,
) -> None:
    """Register a tool with FastMCP + mirror the wire-truth in our registry.

    Tool functions MUST have typed Pydantic signatures — the input parameter
    should be a BaseModel-derived class, and the return type should be a
    BaseModel for `outputSchema` to surface on the wire. Story specs for
    mcp-02..05 follow this exactly.

    After `server.add_tool` runs, we fetch FastMCP's derived schemas and
    store them in `_REGISTERED_TOOLS[name]` — keeping a single source of
    truth between the wire surface and the test registry.
    """
    if name in _REGISTERED_TOOLS:
        msg = f"duplicate tool: {name}"
        raise ValueError(msg)
    server.add_tool(
        fn=fn,  # type: ignore[arg-type]
        name=name,
        description=description,
    )
    # Source the wire-emitted schemas from FastMCP's internal tool manager.
    # Yes, we read `_tool_manager._tools` — FastMCP doesn't expose a sync
    # public reader, and we need the post-add_tool derived view. This is
    # an SDK-version coupling we'll have to revisit if FastMCP refactors.
    fastmcp_tool = server._tool_manager._tools[name]  # noqa: SLF001
    _REGISTERED_TOOLS[name] = RegisteredTool(
        name=name,
        fn=fn,
        input_schema=fastmcp_tool.parameters,
        outputSchema=fastmcp_tool.output_schema,
        description=description,
    )


# --- _ping no-op tool ---------------------------------------------------
#
# The cheapest health-probe surface. Returns a static ALLOW Verdict so
# the Splunk app's dashboard heartbeat panel can poll without needing
# valid input or live judges. Stays registered after stories mcp-02..05
# land — it's the canonical "is the server up?" check.


async def _ping() -> Verdict:
    """No-op health check. Returns a static ALLOW verdict.

    Takes no args — the tool exists only to verify protocol round-trip.
    Typed `-> Verdict` return is load-bearing: FastMCP derives the
    outputSchema from this annotation, so `_ping` registers with
    VERDICT_OUTPUT_SCHEMA as its wire-emitted outputSchema. Without
    the typed return, downstream tools couldn't trust the schema
    derivation pattern.
    """
    return Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation="health check (no-op)",
        surface="mcp_score",
        latency_ms=0.0,
    )


def ensure_ping_registered() -> None:
    """Idempotent _ping registration. Called at module import + by tests.

    Tests that clear `_REGISTERED_TOOLS` for isolation can call this to
    restore the canonical `_ping` registration without re-importing the
    module. `_REGISTERED_TOOLS` is the source of truth for "is it
    registered" — no separate boolean flag needed.
    """
    if "_ping" in _REGISTERED_TOOLS:
        return
    # Test-isolation reset path: tests clear `_REGISTERED_TOOLS` for
    # isolation but FastMCP's `_tool_manager._tools` keeps its own entry.
    # Pop here so a re-call of this helper from a test re-registers
    # cleanly without "duplicate tool" errors from FastMCP. NOT a
    # production defensive guard — production never has _ping cleared.
    server._tool_manager._tools.pop("_ping", None)  # noqa: SLF001
    register_tool(
        name="_ping",
        fn=_ping,
        description="Health-probe no-op. Returns a static ALLOW verdict.",
    )


# --- Transport resolution -----------------------------------------------
#
# Per the MCP spec (`context/10-standards/01-mcp-spec-deep.md`), clients
# SHOULD support stdio whenever possible. stdio is our default. Streamable
# HTTP is opt-in via the `SPLUNKGATE_MCP_TRANSPORT` env var; it binds
# 127.0.0.1 only and validates the Origin header per the spec's DNS-
# rebinding mitigation. Both behaviors land in Tasks 8-9.

Transport = Literal["stdio", "http"]


def resolve_transport() -> Transport:
    """Read SPLUNKGATE_MCP_TRANSPORT; default to stdio.

    Raises ConfigError on unknown values so misconfiguration surfaces at
    startup (when __main__.py calls this), not during the first protocol
    message — easier to diagnose, fail-fast per the no-silent-failure rule.
    """
    raw = os.environ.get("SPLUNKGATE_MCP_TRANSPORT", "stdio")
    normalized = raw.lower()
    if normalized == "stdio":
        return "stdio"
    if normalized == "http":
        return "http"
    # Diagnostic preserves the user's original casing so e.g. an envvar
    # typo of "STDIO " (with a trailing space) is visible in the error.
    msg = f"SPLUNKGATE_MCP_TRANSPORT must be 'stdio' or 'http', got {raw!r}"
    raise ConfigError(msg)


# --- Entry points -------------------------------------------------------
#
# HTTP_BIND_HOST is locked to 127.0.0.1 per the MCP spec's DNS-rebinding
# mitigation guidance — the server MUST NOT bind 0.0.0.0 because then a
# malicious page in the user's browser could reach it via the Origin
# bypass. HTTP_BIND_PORT is the SplunkGate-chosen port that does NOT
# conflict with Splunk's MCP Server (which serves at :8089/services/mcp
# under their REST surface).

HTTP_BIND_HOST = "127.0.0.1"
HTTP_BIND_PORT = 8765


async def serve_stdio() -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects.

    Default transport per MCP spec — clients SHOULD support stdio whenever
    possible. Most MCP-aware hosts (Claude Desktop, Cursor) launch us via
    subprocess + pipe to stdin/stdout.
    """
    await server.run_stdio_async()


async def serve_http() -> None:
    """Run the MCP server over Streamable HTTP bound to 127.0.0.1.

    Uses `build_http_app` so the Origin-check middleware is applied to
    every request. Runs uvicorn directly (rather than FastMCP's helper)
    because we want control over the ASGI app stack — specifically, the
    OriginCheckMiddleware MUST run before FastMCP's protocol handlers.
    """
    import uvicorn  # noqa: PLC0415

    app = build_http_app()
    config = uvicorn.Config(
        app,
        host=HTTP_BIND_HOST,
        port=HTTP_BIND_PORT,
        log_level="info",
    )
    await uvicorn.Server(config).serve()


# --- HTTP Origin validation (MCP DNS-rebinding mitigation) --------------
#
# Per context/10-standards/01-mcp-spec-deep.md: "The HTTP transport MUST
# validate the Origin header." Allowed origins are exactly the localhost
# family (127.0.0.1 / localhost / [::1]). Missing Origin is REJECTED —
# stdio-bridge clients never hit this middleware (they use the STDIO
# transport, not HTTP), so any HTTP request without Origin is either a
# misconfigured client or a DNS-rebinding attempt that omitted the
# header to bypass the check. Per security-review M1 finding.

_ALLOWED_ORIGIN_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})


def _is_allowed_origin(origin_header: str | None) -> bool:
    """Return True only if Origin is present, well-formed, and localhost.

    Missing Origin is rejected: MCP spec requires Origin validation on
    every HTTP request, and stdio clients don't use HTTP. A missing
    header on the HTTP path means either a broken client or a malicious
    actor exploiting browser quirks (e.g. `fetch(url, {mode:'no-cors'})`)
    to bypass the check via DNS rebinding to 127.0.0.1.
    """
    if origin_header is None:
        return False
    # Strip surrounding whitespace defensively (HTTP header values can
    # carry leading/trailing OWS per RFC 7230 §3.2.4).
    cleaned = origin_header.strip()
    if "://" not in cleaned:
        # No scheme — malformed per RFC 6454. Reject.
        return False
    # Origin is `scheme://host[:port]` per RFC 6454. Drop the scheme
    # prefix, then the optional `:port` suffix. The remainder is the host.
    host = cleaned.split("://", 1)[1].split(":", 1)[0]
    return host in _ALLOWED_ORIGIN_HOSTS


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin POSTs with HTTP 403.

    Applied to the Starlette ASGI app built by `build_http_app`. The
    middleware runs BEFORE the FastMCP protocol handler, so rejected
    requests never touch the MCP routing layer.
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Reject cross-origin requests with 403, pass everything else through."""
        origin = request.headers.get("origin")
        if not _is_allowed_origin(origin):
            return Response(status_code=403, content=b"Origin not allowed")
        return await call_next(request)


def build_http_app() -> Starlette:
    """Build the Starlette ASGI app with Origin-check middleware applied.

    Extracted as its own function so tests can exercise the middleware
    without spinning up a real uvicorn worker. Production `serve_http`
    (below) calls this then hands the app to uvicorn — exactly ONCE
    per process. Tests that need a fresh app per case use the
    `reset_session_manager` fixture in test_server_skeleton.py.
    """
    app: Starlette = server.streamable_http_app()
    app.add_middleware(OriginCheckMiddleware)
    return app


# Register _ping at import time so `tools/list` works immediately.
ensure_ping_registered()

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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

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

from datetime import UTC, datetime  # noqa: E402
from uuid import uuid4  # noqa: E402

from splunkgate_core.verdict import Severity, Verdict, VerdictLabel  # noqa: E402


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
    # FastMCP raises if a tool is already registered there too — clear it
    # alongside _REGISTERED_TOOLS so tests can re-call this helper safely.
    server._tool_manager._tools.pop("_ping", None)  # noqa: SLF001
    register_tool(
        name="_ping",
        fn=_ping,
        description="Health-probe no-op. Returns a static ALLOW verdict.",
    )


# Register _ping at import time so `tools/list` works immediately.
ensure_ping_registered()

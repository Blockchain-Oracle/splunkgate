"""SplunkGate MCP server bootstrap on the official `mcp` Python SDK.

Per docs/architecture.md ADR-004 + ADR-004a, SplunkGate runs its OWN
MCP server alongside Splunk MCP Server (Splunkbase app 7931) and SAIA
(app 7245). The three prefixes (`splunk_*`, `saia_*`, `splunkgate_*`)
partition cleanly in any multi-server MCP client config.

This module owns:
- The `FastMCP` server instance (the SDK boundary)
- A `register_tool(name, fn, input_schema, output_schema, description)`
  helper that (a) wires the tool into the FastMCP protocol surface AND
  (b) records it in our internal `_REGISTERED_TOOLS` dict
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


# A tool function: takes a kwargs dict, returns a dict the SDK serializes
# to MCP `structuredContent`. Async because AI Defense + Splunk REST calls
# are async; the type matches the FastMCP tool signature.
ToolFn = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Source-of-truth record for a registered MCP tool.

    Stored in `_REGISTERED_TOOLS` at registration time. Tests enumerate
    these via `_test_helpers.list_tools_for_test()` because FastMCP's
    `list_tools()` is exposed via the MCP protocol's async `tools/list`
    method, not as a sync registry call.

    Attribute name `outputSchema` (camelCase) deliberately mirrors the
    MCP wire-protocol field name — tests assert against it via the same
    spelling MCP clients see.
    """

    name: str
    fn: ToolFn
    input_schema: dict[str, Any]
    outputSchema: dict[str, Any]  # noqa: N815  (camelCase mirrors MCP wire-protocol field name)
    description: str


# The registry. Tests read this via _test_helpers; production reads via
# FastMCP's tool-call protocol surface (which we wire below in register_tool).
_REGISTERED_TOOLS: dict[str, RegisteredTool] = {}


def register_tool(
    *,
    name: str,
    fn: ToolFn,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    description: str,
) -> None:
    """Register a tool with both FastMCP (protocol) and our registry (tests).

    Downstream stories (mcp-02 through mcp-05) call this from their tool
    modules. Signature is locked per docs/stories/story-mcp-01-*.md notes.
    """
    _REGISTERED_TOOLS[name] = RegisteredTool(
        name=name,
        fn=fn,
        input_schema=input_schema,
        outputSchema=output_schema,
        description=description,
    )
    server.add_tool(
        fn=fn,  # type: ignore[arg-type]
        name=name,
        description=description,
    )

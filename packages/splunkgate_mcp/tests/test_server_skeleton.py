"""Behavioral tests for story-mcp-01: SplunkGate MCP server skeleton."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import splunkgate_mcp
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel
from splunkgate_mcp._test_helpers import list_tools_for_test
from splunkgate_mcp.otel import MCP_PROTOCOL_VERSION, build_span_attributes
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_mcp.server import (
    _REGISTERED_TOOLS,
    ensure_ping_registered,
    register_tool,
    server,
)


def test_version_is_0_1_0() -> None:
    """Package version bumped from 0.0.1 stub to 0.1.0 first-real-skeleton."""
    assert splunkgate_mcp.__version__ == "0.1.0"


def test_verdict_output_schema_matches_pydantic() -> None:
    """schemas.VERDICT_OUTPUT_SCHEMA must equal Verdict.model_json_schema()."""
    assert Verdict.model_json_schema() == VERDICT_OUTPUT_SCHEMA


def test_otel_span_attributes_contains_required_keys() -> None:
    """build_span_attributes returns dict with the 3 required keys."""
    attrs = build_span_attributes(session_id="abc123", method_name="tools/call")

    assert attrs["mcp.method.name"] == "tools/call"
    assert attrs["mcp.session.id"] == "abc123"
    assert attrs["mcp.protocol.version"] == "2025-11-25"


def test_otel_span_attributes_protocol_version_is_2025_11_25() -> None:
    """MCP protocol version is the Stable 2025-11-25 (NOT 2025-03-26)."""
    assert MCP_PROTOCOL_VERSION == "2025-11-25"


def test_server_module_imports_official_mcp_sdk() -> None:
    """The `server` instance is from the official `mcp` SDK, not a fork."""
    assert type(server).__module__.startswith("mcp.")


def test_register_tool_uses_fastmcp_derived_schemas() -> None:
    """register_tool sources schemas from FastMCP, not from kwargs.

    This is the wire-truth contract: RegisteredTool.outputSchema reflects
    what MCP clients see, not what we passed in. Test fn returns a Verdict
    so FastMCP derives VERDICT_OUTPUT_SCHEMA correctly.
    """
    _REGISTERED_TOOLS.clear()
    # Also clear FastMCP's internal registry so re-registration doesn't collide
    server._tool_manager._tools.pop("_test_tool", None)  # noqa: SLF001

    async def typed_fn() -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mcp_score",
            latency_ms=0.0,
        )

    register_tool(name="_test_tool", fn=typed_fn, description="Test tool")

    assert "_test_tool" in _REGISTERED_TOOLS
    entry = _REGISTERED_TOOLS["_test_tool"]
    assert entry.name == "_test_tool"
    # FastMCP derived the schema from the typed return — must equal VERDICT_OUTPUT_SCHEMA
    assert entry.outputSchema == VERDICT_OUTPUT_SCHEMA
    assert callable(entry.fn)


def test_list_tools_for_test_returns_registered_tools() -> None:
    """_test_helpers exposes the internal registry without async FastMCP surface."""
    _REGISTERED_TOOLS.clear()
    server._tool_manager._tools.pop("_helper_test", None)  # noqa: SLF001

    async def typed_fn() -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mcp_score",
            latency_ms=0.0,
        )

    register_tool(name="_helper_test", fn=typed_fn, description="x")

    tools = list_tools_for_test()
    names = [t.name for t in tools]
    assert "_helper_test" in names
    target = next(t for t in tools if t.name == "_helper_test")
    assert target.outputSchema == VERDICT_OUTPUT_SCHEMA


def test_ping_tool_registered_at_bootstrap() -> None:
    """_ping no-op tool registers automatically with VERDICT_OUTPUT_SCHEMA."""
    ensure_ping_registered()

    assert "_ping" in _REGISTERED_TOOLS
    ping = _REGISTERED_TOOLS["_ping"]
    assert ping.outputSchema == VERDICT_OUTPUT_SCHEMA

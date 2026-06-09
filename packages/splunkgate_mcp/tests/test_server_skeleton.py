"""Behavioral tests for story-mcp-01: SplunkGate MCP server skeleton."""

from __future__ import annotations

import splunkgate_mcp
from splunkgate_core.verdict import Verdict
from splunkgate_mcp.otel import MCP_PROTOCOL_VERSION, build_span_attributes
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_mcp.server import _REGISTERED_TOOLS, register_tool, server


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


def test_register_tool_adds_to_internal_registry() -> None:
    """register_tool populates _REGISTERED_TOOLS with a RegisteredTool entry."""
    # Clean slate for the test
    _REGISTERED_TOOLS.clear()

    async def noop_fn(args: dict[str, object]) -> dict[str, object]:  # noqa: ARG001
        return {"verdict": "ALLOW"}

    register_tool(
        name="_test_tool",
        fn=noop_fn,
        input_schema={"type": "object"},
        output_schema=VERDICT_OUTPUT_SCHEMA,
        description="Test tool",
    )

    assert "_test_tool" in _REGISTERED_TOOLS
    entry = _REGISTERED_TOOLS["_test_tool"]
    assert entry.name == "_test_tool"
    assert entry.outputSchema == VERDICT_OUTPUT_SCHEMA
    assert entry.input_schema == {"type": "object"}
    assert callable(entry.fn)

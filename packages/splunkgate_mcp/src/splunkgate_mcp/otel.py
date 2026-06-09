"""OTel attribute builder for SplunkGate MCP server spans.

Per context/10-standards/02-otel-genai-semantic-conventions.md, MCP
sub-convention attributes (`mcp.method.name`, `mcp.session.id`,
`mcp.protocol.version`) co-emit with the `gen_ai.evaluation.result`
event that `splunkgate_core.otel` produces. This module exposes the
attribute builder; the actual evaluation event emission stays in
splunkgate_core (we reuse, do not duplicate).
"""

from __future__ import annotations

# MCP spec version per context/10-standards/01-mcp-spec-deep.md (Stable).
# Do NOT hardcode "2025-03-26" — that's Splunk's older version per the
# CiscoDevNet README.
MCP_PROTOCOL_VERSION = "2025-11-25"


def build_span_attributes(*, session_id: str, method_name: str) -> dict[str, str]:
    """Build the dict of MCP sub-convention attributes for a tool-call span.

    The caller wraps each tool invocation in a SERVER-kind span named
    `{method_name} {tool_name}` per the OTel GenAI semconv guidance and
    sets these attributes on it.
    """
    return {
        "mcp.method.name": method_name,
        "mcp.session.id": session_id,
        "mcp.protocol.version": MCP_PROTOCOL_VERSION,
    }

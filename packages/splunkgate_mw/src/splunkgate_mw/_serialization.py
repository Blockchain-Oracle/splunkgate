"""Tool-call serialization helper for SplunkGate middleware (story-mw-02).

Produces the canonical text payload sent to Cisco AI Defense Inspection
API when escalating a tool call. Matches the shape used by the MCP twin
(`splunkgate_mcp.tools.judge_tool_call`) so verdicts emitted from
Surface 1 (middleware) and Surface 2 (MCP) are directly comparable on
the Splunk app dashboards.

Keep this module tiny — its only job is to deterministically render a
ToolCall to a single string. Sorting keys gives bit-stable output for
caching + audit-trail diffing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from splunklib.ai.messages import ToolCall

__all__ = ["serialize_tool_call"]


def serialize_tool_call(call: ToolCall) -> str:
    """Render a ToolCall to the canonical AI Defense payload string.

    Shape: ``"<tool_name>(<json-sorted-args>)"``. Matches the MCP twin's
    serialization so verdicts on the same (tool_name, tool_args) pair
    are byte-identical between Surface 1 and Surface 2.

    `ensure_ascii=False` keeps non-ASCII payload characters intact for
    regex matching upstream; `sort_keys=True` gives deterministic output
    regardless of insertion order.
    """
    args_json = json.dumps(call.args, sort_keys=True, ensure_ascii=False)
    return f"{call.name}({args_json})"

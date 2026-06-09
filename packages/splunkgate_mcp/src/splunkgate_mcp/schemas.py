"""Output schemas exposed by the SplunkGate MCP server's tools.

Per docs/plans/2026-06-09-mcp-design.md § Architecture, every tool's
`outputSchema` is derived from a Pydantic model via `model_json_schema()`
so MCP protocol-level validation catches schema drift at the server
boundary.

This module exposes only the Verdict schema. The AuditReport schema
(for story-mcp-05's `splunkgate_audit_trace`) joins in a later PR.
"""

from __future__ import annotations

from typing import Any

from splunkgate_core.verdict import Verdict

VERDICT_OUTPUT_SCHEMA: dict[str, Any] = Verdict.model_json_schema()

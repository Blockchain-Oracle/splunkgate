"""Output schemas exposed by the SplunkGate MCP server's tools.

Per docs/plans/2026-06-09-mcp-design.md § Architecture, every tool's
`outputSchema` is derived from a Pydantic model via `model_json_schema()`
so MCP protocol-level validation catches schema drift at the server
boundary.

VERDICT_OUTPUT_SCHEMA is the schema for mcp-02 / mcp-03 / mcp-04 tools.
AUDIT_REPORT_OUTPUT_SCHEMA is the schema for mcp-05's
`splunkgate_audit_trace` — the only tool whose return type is the
aggregate `AuditReport`, NOT a per-event `Verdict`.
"""

from __future__ import annotations

from typing import Any

from splunkgate_core.audit_report import AuditReport
from splunkgate_core.verdict import Verdict

VERDICT_OUTPUT_SCHEMA: dict[str, Any] = Verdict.model_json_schema()
AUDIT_REPORT_OUTPUT_SCHEMA: dict[str, Any] = AuditReport.model_json_schema()

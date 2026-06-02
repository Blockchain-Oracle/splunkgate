# Story — MCP tool `aegis_audit_trace`

**ID:** story-mcp-05-tool-audit-trace
**Epic:** EPIC-07 — Surface 2 Aegis MCP Server (own server, parallel to Splunk's)
**Depends on:** story-mcp-01-server-skeleton-with-mcp-python-sdk
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** SOC analyst (or compliance examiner, or regulator) wanting "show me everything Aegis judged for trace_id X across all surfaces"
**I want to** call MCP tool `aegis_audit_trace(trace_id, eval_dimensions?)` that queries Splunk via REST search, aggregates all `cisco_ai_defense:aegis_verdict` events for that trace, and returns a typed `AuditReport`
**So that** the regulator-evidence-pack dashboard (Surface 4) and external auditors have a single MCP-callable surface for "the audit trail of agent decisions" — without needing direct Splunk credentials or SPL fluency

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_core/src/aegis_core/audit_report.py` — NEW — `class AuditReport(BaseModel): trace_id: UUID; event_count: int; verdicts: list[Verdict]; first_seen: datetime; last_seen: datetime; surfaces_seen: list[str]; aggregate: dict` — shared type so Surface 4 dashboards can deserialize the same shape
- `packages/aegis_mcp/src/aegis_mcp/tools/audit_trace.py` — NEW — MCP tool; `class AuditTraceInputs(BaseModel): trace_id: UUID; eval_dimensions: list[str] = ["verdict","severity","surface"]`; `async def audit_trace(args: AuditTraceInputs) -> AuditReport`; runs Splunk REST search via `aegis_judges.foundation_sec` (which already wraps Splunk REST search per EPIC-05); SPL: `search index=main sourcetype=cisco_ai_defense:aegis_verdict trace_id={trace_id} | stats count by {eval_dimensions}`; aggregates the rows into the `AuditReport` shape; `surface="mcp_audit"`; emits OTel evaluation event tagged with `aegis.audit.event_count`
- `packages/aegis_mcp/src/aegis_mcp/schemas.py` — UPDATE — export `AUDIT_REPORT_OUTPUT_SCHEMA = AuditReport.model_json_schema()` alongside `VERDICT_OUTPUT_SCHEMA`
- `packages/aegis_mcp/src/aegis_mcp/server.py` — UPDATE — wire `audit_trace.register(server)` into bootstrap; this tool's `outputSchema` is `AUDIT_REPORT_OUTPUT_SCHEMA` (not the Verdict schema — audit is the one tool that returns an aggregate)
- `packages/aegis_mcp/tests/test_tool_audit_trace.py` — NEW — ≥ 12 behavioral tests: tool discoverable via `tools/list`, `outputSchema` equals `AuditReport.model_json_schema()`, valid trace_id with 3 mocked Splunk-returned events → `event_count == 3` and `len(verdicts) == 3`, `surfaces_seen` matches the union of surfaces in returned events, `first_seen <= last_seen`, default eval_dimensions used when not provided, custom eval_dimensions=["severity"] passed through to SPL string verbatim, surface field of the wrapper event (OTel) == "mcp_audit", `aegis.audit.event_count` attribute set on emitted event, in-band `isError: true` on Splunk REST failure, empty-result trace_id returns `event_count == 0` with empty verdicts list (not isError), SPL injection attempt in eval_dimensions rejected with `AegisValidationError`

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the server is bootstrapped
When  the MCP `tools/list` request is sent in-process
Then  the response contains a tool named exactly "aegis_audit_trace"
And   that tool's `outputSchema` deep-equals `AuditReport.model_json_schema()`

Given a valid trace_id and a Splunk-mock that returns 3 events for that trace_id
When  the tool is called with eval_dimensions=["verdict","severity","surface"]
Then  the returned AuditReport has event_count == 3
And   len(verdicts) == 3
And   first_seen <= last_seen

Given a Splunk-mock that returns 0 events for trace_id
When  the tool is called
Then  the returned AuditReport has event_count == 0
And   verdicts is an empty list
And   the MCP result has isError == false (empty result is not an error)

Given eval_dimensions=["severity"]
When  the tool is called and the SPL request is captured
Then  the captured SPL contains the substring "by severity"
And   the captured SPL contains "sourcetype=cisco_ai_defense:aegis_verdict"

Given eval_dimensions=["severity; | delete"]   # SPL injection attempt
When  the tool is called
Then  the tool raises AegisValidationError before any Splunk REST request is issued
And   the MCP result has isError == true

Given the Splunk REST client raises AegisSplunkError (simulated 5xx)
When  the tool is called
Then  the MCP result has isError == true (in-band per MCP spec)

Given an OTel in-test exporter is attached
When  the tool is called once
Then  exactly one event with name "gen_ai.evaluation.result" is recorded
And   that event has attribute `aegis.surface` == "mcp_audit"
And   that event has attribute `aegis.audit.event_count` set to the integer count

Given the test file exists
When  `uv run pytest packages/aegis_mcp/tests/test_tool_audit_trace.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the production source
When  `wc -l packages/aegis_mcp/src/aegis_mcp/tools/audit_trace.py` runs
Then  the line count is ≤ 400

Given the §14 grep runs on production code
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/aegis_mcp/tools/audit_trace.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tool is registered and exposes AUDIT_REPORT_OUTPUT_SCHEMA
uv run python -c "
import asyncio
from aegis_mcp.server import server
from aegis_mcp.schemas import AUDIT_REPORT_OUTPUT_SCHEMA
from aegis_core.audit_report import AuditReport
assert AUDIT_REPORT_OUTPUT_SCHEMA == AuditReport.model_json_schema()
tools = asyncio.run(server.list_tools())
names = [t.name for t in tools]
assert 'aegis_audit_trace' in names, names
target = next(t for t in tools if t.name == 'aegis_audit_trace')
assert target.outputSchema == AUDIT_REPORT_OUTPUT_SCHEMA
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/aegis_mcp/tests/test_tool_audit_trace.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# SPL injection rejected before issuing REST request
uv run python -c "
import asyncio, uuid
from aegis_mcp.tools.audit_trace import audit_trace, AuditTraceInputs
try:
    asyncio.run(audit_trace(AuditTraceInputs(
        trace_id=uuid.uuid4(),
        eval_dimensions=['severity; | delete'],
    )))
    raise SystemExit('should have raised AegisValidationError')
except Exception as e:
    assert type(e).__name__ == 'AegisValidationError'
print('OK')
"
# Must print 'OK'

# 400-LOC cap
wc -l packages/aegis_mcp/src/aegis_mcp/tools/audit_trace.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/aegis_mcp/tools/audit_trace.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source — we run our own server alongside, NOT register into it.** This tool intentionally lives on Aegis's own server because Splunk's MCP Server has no documented plugin mechanism (its `splunk_run_query` tool overlaps in capability but cannot be extended to enforce our trace_id + sourcetype filter).
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP tools support `structuredContent` + `outputSchema` for rich validated verdicts.** This tool returns `AuditReport` (an aggregate), not `Verdict` — it's the only Aegis MCP tool with a non-Verdict output schema. Both schemas are derived from Pydantic via `model_json_schema()`.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, tool execution errors are reported in-band via `isError: true`.** Splunk REST 5xx → in-band error. An empty-result query is NOT an error — return an `AuditReport` with `event_count=0`.
- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`) co-emit with `gen_ai.evaluation.result` events.** This tool also adds the custom `aegis.audit.event_count` attribute — semantically a span attribute extension, intended for upstream proposal post-hackathon.
- **Per `docs/architecture.md` ADR-005, Aegis events emit to `cisco_ai_defense:aegis_verdict` sourcetype** (Cisco Security Cloud namespace, verified live on Abu's Splunk Cloud instance). The SPL string MUST use that exact sourcetype.
- **`eval_dimensions` is an allowlist parameter — SPL-injection-safe.** Validate against a strict allowlist: `{"verdict", "severity", "surface", "rules", "classifications", "tool_name", "agent_id"}`. Anything else → `AegisValidationError` BEFORE issuing the REST call. Do NOT interpolate user-controlled strings into SPL.
- **Per `docs/architecture.md` § "API schemas", `Verdict.surface` for the OTel event wrapping this tool's invocation is the literal string `"mcp_audit"`.** Surface 4 dashboards filter on this exact string.
- Splunk REST search client is `aegis_judges.foundation_sec.run_search(...)` from EPIC-05. That client already handles auth (token from `AEGIS_SPLUNK_HEC_TOKEN` env var or equivalent) and respects the `AEGIS_DEV_INSECURE_TLS=1` escape hatch per `docs/architecture.md` hard rule §7.
- The aggregate `AuditReport.aggregate` field is a freeform dict that mirrors the SPL `stats` output (e.g., `{"BLOCK": 2, "ALLOW": 1}` for a `stats count by verdict`). Keep it as `dict[str, Any]` to avoid forcing a schema where the inputs vary by `eval_dimensions`.
- For tests, use `respx` for Splunk REST HTTP mocking. Provide a fixture file `packages/aegis_mcp/tests/fixtures/splunk_audit_3events.json` with 3 representative `aegis_verdict` events spanning all four surfaces.
- The `AuditReport` schema lives in `aegis_core` (not `aegis_mcp`) so Surface 4 dashboards (which import from `aegis_core` per architecture) can deserialize the same shape without coupling to the MCP package.

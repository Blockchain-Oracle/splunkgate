# Story — MCP tool `splunkgate_judge_tool_call`

**ID:** story-mcp-03-tool-judge-tool-call
**Epic:** EPIC-07 — Surface 2 SplunkGate MCP Server (own server, parallel to Splunk's)
**Depends on:** story-mcp-01-server-skeleton-with-mcp-python-sdk
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** developer running an LLM agent that's about to invoke a downstream tool (shell, SQL, HTTP fetch, file write, etc.)
**I want to** call MCP tool `splunkgate_judge_tool_call(tool_name, tool_args)` that returns a typed `Verdict` — ALLOW pass-through / BLOCK refusal / MODIFY with suggested-mod / REVIEW for human-in-the-loop
**So that** my agent can ask SplunkGate "is this tool invocation safe?" before executing, with judgment routed through DefenseClaw's local rule-pack first (cheap, deterministic) and escalated to Cisco AI Defense only when ambiguous

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py` — NEW — MCP tool definition; `class JudgeToolCallInputs(BaseModel): tool_name: str; tool_args: dict[str, Any]`; `async def judge_tool_call(args: JudgeToolCallInputs) -> Verdict`; routes through `splunkgate_judges.defenseclaw_backend.evaluate_tool_call(...)` rule-pack first, escalates ambiguous cases to `splunkgate_judges.ai_defense.inspect(...)` with the args serialized as text; on MODIFY, populates `Verdict.modifications = {"suggested_args": {...}}` with the redacted/safer arg dict; `surface="mcp_judge_tool"`; emits OTel evaluation event
- `packages/splunkgate_mcp/src/splunkgate_mcp/server.py` — UPDATE — wire `judge_tool_call.register(server)` into bootstrap so the tool surfaces in `tools/list`
- `packages/splunkgate_mcp/tests/test_tool_judge_tool_call.py` — NEW — ≥ 12 behavioral tests: tool discoverable via `tools/list`, `outputSchema` equals `Verdict.model_json_schema()`, benign tool_name="get_weather" with safe args → ALLOW, tool_name="shell_exec" with `cmd="rm -rf /"` → BLOCK with rule hit from DefenseClaw rule-pack, tool_name="send_email" with PII in body → MODIFY with `modifications.suggested_args` containing redacted body, surface == "mcp_judge_tool" on every verdict, latency_ms populated, trace_id is valid UUID, ambiguous case escalates to AI Defense (mocked via respx), OTel evaluation event emitted with `splunkgate.surface == "mcp_judge_tool"`, in-band `isError: true` on judge failure, modifications field is omitted (not null) on non-MODIFY verdicts

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the server is bootstrapped
When  `list_tools_for_test()` (from `splunkgate_mcp._test_helpers`, owned by story-mcp-01) is called
Then  the returned list contains a tool named exactly "splunkgate_judge_tool_call"
And   that tool's `outputSchema` deep-equals `Verdict.model_json_schema()`

Given tool_name="get_weather" and tool_args={"city": "Toronto"}
When  the tool is called
Then  the verdict field equals "ALLOW"
And   the surface field equals "mcp_judge_tool"
And   the modifications field is None (or omitted)

Given tool_name="shell_exec" and tool_args={"cmd": "rm -rf /"}
When  the tool is called
Then  the verdict field equals "BLOCK"
And   the severity is "HIGH"
And   rules contains at least one entry with source == "defenseclaw_regex"

Given tool_name="send_email" and tool_args contains a US SSN pattern in the body
When  the tool is called
Then  the verdict field equals "MODIFY"
And   the modifications field is a dict containing key "suggested_args"
And   modifications["suggested_args"]["body"] does not contain the original SSN substring

Given an OTel in-test exporter is attached
When  the tool is called once
Then  exactly one event with name "gen_ai.evaluation.result" is recorded
And   that event has attribute `splunkgate.surface` == "mcp_judge_tool"

Given the DefenseClaw rule-pack raises SplunkGateJudgeError (simulated)
When  the tool is called
Then  the MCP result has isError == true (in-band per MCP spec)

Given the test file exists
When  `uv run pytest packages/splunkgate_mcp/tests/test_tool_judge_tool_call.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the production source
When  `wc -l packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py` runs
Then  the line count is ≤ 400

Given the §14 grep runs on production code
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tool is registered
# Use the test helper from story-mcp-01 (FastMCP's protocol surface is not a sync registry)
uv run python -c "
from splunkgate_mcp._test_helpers import list_tools_for_test
tools = list_tools_for_test()
names = [t.name for t in tools]
assert 'splunkgate_judge_tool_call' in names, names
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/splunkgate_mcp/tests/test_tool_judge_tool_call.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# BLOCK path smoke
uv run python -c "
import asyncio
from splunkgate_mcp.tools.judge_tool_call import judge_tool_call, JudgeToolCallInputs
v = asyncio.run(judge_tool_call(JudgeToolCallInputs(tool_name='shell_exec', tool_args={'cmd': 'rm -rf /'})))
assert v.verdict.value == 'BLOCK'
assert v.surface == 'mcp_judge_tool'
print('OK')
"
# Must print 'OK'

# MODIFY path returns suggested args
uv run python -c "
import asyncio
from splunkgate_mcp.tools.judge_tool_call import judge_tool_call, JudgeToolCallInputs
v = asyncio.run(judge_tool_call(JudgeToolCallInputs(
    tool_name='send_email',
    tool_args={'to':'a@b.com','body':'My SSN is 123-45-6789'}
)))
if v.verdict.value == 'MODIFY':
    assert 'suggested_args' in (v.modifications or {})
    assert '123-45-6789' not in v.modifications['suggested_args']['body']
print('OK')
"
# Must print 'OK'

# 400-LOC cap
wc -l packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source — we run our own server alongside, NOT register into it.** This tool's `splunkgate_` prefix avoids collision with Splunk's `splunk_*` tools, including their beta `splunk_run_saved_search`.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP tools support `structuredContent` + `outputSchema` for rich validated verdicts.** The `Verdict.modifications` field carries the suggested-arg dict on MODIFY verdicts — keep it as a freeform dict per the architecture spec; downstream clients can introspect via the `outputSchema` (it's defined as `dict | None`).
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, tool execution errors are reported in-band via `isError: true`, NOT as JSON-RPC errors.** Wrap the judge call in try/except for `SplunkGateJudgeError` and convert to in-band errors per spec.
- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`) co-emit with `gen_ai.evaluation.result` events.** Reuse `splunkgate_core.otel` — do not re-implement.
- **DefenseClaw rule-pack is the cheap first-pass classifier per `docs/architecture.md` § "Surface 3".** Call `splunkgate_judges.defenseclaw_backend.evaluate_tool_call(tool_name, tool_args)` first. Per the audit (`../../../context/HALLUCINATION-AUDIT.md` H-44/H-45), DefenseClaw is a Go dependency we depend on but do NOT rebuild; the `defenseclaw_backend` Python module wraps the rule-pack subset we ported for cheap in-process matching (regex rules for `shell_exec`, `rm -rf`, base64 payload, SSN, common PII patterns).
- **Per `docs/architecture.md` § "API schemas", `Verdict.surface` for this tool is the literal string `"mcp_judge_tool"`.** Surface 4 dashboards filter on this exact string.
- For MODIFY verdicts, the `modifications.suggested_args` dict carries the same keys as the input `tool_args`, with PII/dangerous-token redactions applied. Do NOT silently drop fields — every original key must appear in the output, even if its value was redacted to `"[REDACTED:PII]"`.
- The tool_args dict is opaque — agents pass arbitrary structures. Cap serialized size at 64 KB (raise `SplunkGateValidationError` if exceeded) so we don't blow out the AI Defense API request limit.
- Test fixtures for DefenseClaw rule-pack live at `packages/splunkgate_judges/tests/fixtures/defenseclaw_rules.json` (EPIC-08 lands them). If that file is missing at test time, mark the rule-pack tests xfail with a TODO referencing EPIC-08 — do NOT block this story on EPIC-08.

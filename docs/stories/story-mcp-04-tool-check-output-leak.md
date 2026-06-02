# Story — MCP tool `aegis_check_output_leak`

**ID:** story-mcp-04-tool-check-output-leak
**Epic:** EPIC-07 — Surface 2 Aegis MCP Server (own server, parallel to Splunk's)
**Depends on:** story-mcp-01-server-skeleton-with-mcp-python-sdk, story-judges-05-ai-defense-end-to-end-integration-test
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** developer running an LLM agent that just produced an output (text the user will see, or text the agent will pass to a downstream tool)
**I want to** call MCP tool `aegis_check_output_leak(output_text, sensitivity?)` that returns a typed `Verdict` — ALLOW pass-through / MODIFY with redacted output / BLOCK refusal
**So that** PII, PHI, PCI, and proprietary-credential leaks can be intercepted post-inference using Cisco AI Defense's PII/PHI/PCI rules, with the redacted output handed back inline (no extra round-trip)

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mcp/src/aegis_mcp/tools/check_output_leak.py` — NEW — MCP tool definition; `class CheckOutputLeakInputs(BaseModel): output_text: str; sensitivity: Literal["default","fsi","hipaa","pubsec"] = "default"`; `async def check_output_leak(args: CheckOutputLeakInputs) -> Verdict`; calls `aegis_judges.ai_defense.inspect(text=output_text, rules_enabled=<profile-derived list>)` with the rule subset filtered to the documented PII/PHI/PCI rules ("PII", "PHI", "PCI") per the AI Defense 11-rule catalog; on MODIFY, populates `Verdict.modifications = {"redacted_output": "<text with PII/PHI/PCI replaced by [REDACTED:<rule>] tokens>"}`; `surface="mcp_check_output"`; emits OTel evaluation event
- `packages/aegis_mcp/src/aegis_mcp/server.py` — UPDATE — wire `check_output_leak.register(server)` into bootstrap
- `packages/aegis_mcp/tests/test_tool_check_output_leak.py` — NEW — ≥ 12 behavioral tests: tool discoverable, `outputSchema` equals `Verdict.model_json_schema()`, benign output → ALLOW, output containing US SSN → MODIFY with `modifications.redacted_output` containing `[REDACTED:PII]` and no original SSN substring, output containing PHI (DOB + diagnosis pattern) → MODIFY with `[REDACTED:PHI]`, output containing PCI (16-digit card) → MODIFY with `[REDACTED:PCI]`, sensitivity="hipaa" enables PHI rule explicitly, sensitivity="fsi" enables PCI rule explicitly, surface == "mcp_check_output", latency_ms populated, trace_id valid UUID, OTel evaluation event emitted with `aegis.surface == "mcp_check_output"`, in-band `isError: true` on AI Defense unreachable

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the server is bootstrapped
When  the MCP `tools/list` request is sent in-process
Then  the response contains a tool named exactly "aegis_check_output_leak"
And   that tool's `outputSchema` deep-equals `Verdict.model_json_schema()`

Given output_text="The weather in Toronto today is sunny, 22C."
When  the tool is called with sensitivity="default"
Then  the verdict field equals "ALLOW"
And   the surface field equals "mcp_check_output"

Given output_text contains the literal "123-45-6789" (US SSN pattern)
When  the tool is called (AI Defense mock returns PII hit)
Then  the verdict field equals "MODIFY"
And   modifications["redacted_output"] does not contain the substring "123-45-6789"
And   modifications["redacted_output"] contains the substring "[REDACTED:PII]"

Given output_text contains a 16-digit Luhn-valid credit card number
When  the tool is called with sensitivity="fsi"
Then  the AI Defense request body's rules_enabled list includes "PCI"
And   the verdict field equals "MODIFY"
And   modifications["redacted_output"] contains "[REDACTED:PCI]"

Given output_text contains a DOB + diagnosis pattern
When  the tool is called with sensitivity="hipaa"
Then  the AI Defense request body's rules_enabled list includes "PHI"
And   the verdict field equals "MODIFY"
And   modifications["redacted_output"] contains "[REDACTED:PHI]"

Given an OTel in-test exporter is attached
When  the tool is called once
Then  exactly one event with name "gen_ai.evaluation.result" is recorded
And   that event has attribute `aegis.surface` == "mcp_check_output"

Given the AI Defense client raises AegisJudgeError (simulated upstream 503)
When  the tool is called
Then  the MCP result has isError == true (in-band per MCP spec)

Given the test file exists
When  `uv run pytest packages/aegis_mcp/tests/test_tool_check_output_leak.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the production source
When  `wc -l packages/aegis_mcp/src/aegis_mcp/tools/check_output_leak.py` runs
Then  the line count is ≤ 400

Given the §14 grep runs on production code
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/aegis_mcp/tools/check_output_leak.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Tool is registered
uv run python -c "
import asyncio
from aegis_mcp.server import server
tools = asyncio.run(server.list_tools())
names = [t.name for t in tools]
assert 'aegis_check_output_leak' in names, names
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/aegis_mcp/tests/test_tool_check_output_leak.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# Redaction round-trip smoke
uv run python -c "
import asyncio
from aegis_mcp.tools.check_output_leak import check_output_leak, CheckOutputLeakInputs
v = asyncio.run(check_output_leak(CheckOutputLeakInputs(
    output_text='Patient SSN: 123-45-6789 confirmed.',
    sensitivity='hipaa',
)))
if v.verdict.value == 'MODIFY':
    redacted = (v.modifications or {}).get('redacted_output', '')
    assert '123-45-6789' not in redacted
    assert '[REDACTED:' in redacted
assert v.surface == 'mcp_check_output'
print('OK')
"
# Must print 'OK'

# 400-LOC cap
wc -l packages/aegis_mcp/src/aegis_mcp/tools/check_output_leak.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/aegis_mcp/tools/check_output_leak.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source — we run our own server alongside, NOT register into it.** Tool name `aegis_check_output_leak` uses the `aegis_` prefix to coexist with `splunk_*` and `saia_*`.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP tools support `structuredContent` + `outputSchema` for rich validated verdicts.** The `Verdict.modifications.redacted_output` field is a string carrying the post-redaction text. Clients introspect the freeform `modifications` dict; the architecture spec defines it as `dict | None`.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, tool execution errors are reported in-band via `isError: true`.** AI Defense unreachable → in-band error, NOT JSON-RPC error.
- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`) co-emit with `gen_ai.evaluation.result` events.** Reuse `aegis_core.otel`.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, Cisco AI Defense Inspection API exposes 11 named rules.** The three we filter to here are the literal strings `"PII"`, `"PHI"`, `"PCI"`. Do NOT use lowercased or hyphenated variants — the API rejects unknown rule names.
- **Sensitivity profile → rules_enabled mapping:**
  - `"default"` → `["PII"]`
  - `"fsi"` → `["PII", "PCI"]`
  - `"hipaa"` → `["PII", "PHI"]`
  - `"pubsec"` → `["PII"]` (PubSec profile in `aegis_mw.profiles` is defined in EPIC-06; for MCP we only need PII at the base level here)
- **Per `docs/architecture.md` § "API schemas", `Verdict.surface` for this tool is the literal string `"mcp_check_output"`.** Surface 4 dashboards filter on this exact string.
- The redaction tokens are `[REDACTED:PII]`, `[REDACTED:PHI]`, `[REDACTED:PCI]` — verbatim, including the brackets and the colon. Surface 4 dashboard panels grep these tokens.
- Cisco AI Defense response field is `rules`, NOT `triggered_rules` — per `../../../context/HALLUCINATION-AUDIT.md`. The judges layer types catch this at the boundary; do not re-derive.
- Use `respx` for AI Defense HTTP mocking in tests. The `aegis_judges.ai_defense_mock` fixtures from EPIC-04 are reusable here.
- BLOCK verdicts are reserved for catastrophic-leak signals (severity HIGH on PII/PCI/PHI when policy says "never let this out"); MODIFY is the default path because returning a redacted answer preserves agent utility.

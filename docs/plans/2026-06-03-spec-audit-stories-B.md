# Spec Audit — Stories B (EPICs 5, 6, 7, 8)

Auditor: stories batch B
Date: 2026-06-03
Files audited: 16

## Summary

**8 critical** · **17 minor** · **4 non-issues**

Overall: the batch is in much better shape than typical mid-spec. The architecturally
load-bearing claims (Foundation-Sec as explainer-only, the 4 distinct middleware kwargs,
MCP `2025-11-25`, DefenseClaw line counts) are correct and triple-cited throughout.
But there are seven cross-cutting consistency bugs that will bite the coding agents,
plus a structural problem with the mw-03/mw-04 split that I couldn't verify works as
described. Fixes are mostly mechanical.

---

## Critical findings

### B-C-01 — story-mw-04-model-middleware-post-inference-pii-check.md — Foundation-Sec contract mismatch with EPIC-05 deliverable

**Location:** lines 23, 119 of mw-04; cross-check with foundsec-02 line 23 and foundsec-03 line 24.

**Problem.** mw-04 calls `splunkgate_judges.foundation_sec.explain(verdict, text)` (2-arg
positional: a `Verdict` and the original text). EPIC-05 ships
`FoundationSecExplainer.explain(ctx: VerdictContext) -> str` — a method on a class
instance, taking a `VerdictContext` Pydantic model (NOT a Verdict). The contract names
diverge across stories that are sequenced as dependencies. The coding agent for mw-04
will write a `from splunkgate_judges.foundation_sec import explain` import that does not
resolve, OR will pass a `Verdict` where a `VerdictContext` is expected.

Same bug in mcp-05 line 24 which says `splunkgate_judges.foundation_sec` "already wraps Splunk
REST search per EPIC-05" — actually EPIC-05 ships a `SplunkSearchClient` class plus a
`FoundationSecExplainer` class. There is no module-level `run_search(...)` function
(asserted in mcp-05 line 149).

**Suggested fix.** Add to mw-04 file modification map:
- `packages/splunkgate_mw/src/splunkgate_mw/_explanation_bridge.py` — NEW — adapter
  `verdict_to_context(v: Verdict, text: str) -> VerdictContext` that maps the Verdict
  back into the VerdictContext shape (severity, rules, classifications, offending_text,
  trace_id). Then call
  `await self._explainer.explain(verdict_to_context(verdict, text))`.

In mcp-05 line 24 replace `splunkgate_judges.foundation_sec` with the actual class
`splunkgate_judges.foundation_sec.SplunkSearchClient.from_env()`, then call
`.submit_search(spl, ...)` (the method name shipped in foundsec-01). Update line 149
similarly.

### B-C-02 — story-mw-03 + story-mw-04 — model_middleware.py file-append split will break in practice

**Location:** mw-03 lines 23, 138; mw-04 lines 23, 113.

**Problem.** mw-03 plants the anchor comment `# --- POST-INFERENCE SCAN: see story-mw-04 ---`
AFTER `response = await handler(request)` and BEFORE `return response`. mw-04 says it
"INSERTS the post-inference logic at exactly that anchor". This is fine in a vacuum but
mw-03 also instructs the agent to wire the BLOCK/MODIFY/ALLOW branches in the
pre-inference half (`(e) BLOCK → raise...; (f) MODIFY → ... call handler(new_request);
(g) ALLOW → handler(request)`). If the cheap pre-pass returns BLOCK, the function
raises BEFORE `response = await handler(request)` is ever reached — so the anchor never
executes. mw-04 then has to reckon with: the anchor isn't a seam, it's just a comment
inside the ALLOW branch. The post-inference scan currently only runs on the ALLOW
side of pre-inference, which is correct behaviorally but the spec doesn't say that.

Worse: if mw-03 follows §(f) MODIFY by calling `handler(new_request)` and returning
that response, mw-04's "after `response = await handler(request)`" insertion site is
ambiguous (which call? the ALLOW one or the MODIFY one?). Both must flow through the
post-scan.

**Suggested fix.** Tighten the mw-03 spec:

1. mw-03 must implement pre-inference as a helper `_pre_inference_scan(request) -> Verdict`
   that returns ALLOW/BLOCK/MODIFY without raising; mw-03's `model_middleware` body
   computes the verdict, decides handler input (original vs. redacted), calls handler
   exactly ONCE, then drops through to the anchor. BLOCK still raises but AFTER the
   `response = await ...` line is moved into a pre-anchor "skip" sentinel.
2. Add to mw-04 acceptance criteria: "Given the cheap pre-pass returns BLOCK, no
   post-inference scan runs and no Foundation-Sec call is made (`respx.routes` 0 calls)."
3. mw-04 ACs around AC line 64 currently assert "combined ≤ 400 LOC". Add a per-half
   floor: "mw-03's contribution is ≤ 200 LOC" + "mw-04's contribution adds ≤ 200 LOC"
   AND "combined ≤ 400 LOC" — without all three, an agent that overruns 240 LOC in
   mw-03 forces mw-04 to ship a sub-200-LOC half that still busts the cap.

### B-C-03 — story-mcp-01 — FastMCP+test contract is hand-wavy and will not work

**Location:** mcp-01 lines 25, 30, 88-95 (shell verification).

**Problem.** Story uses `from splunkgate_mcp.server import server` (a module-level singleton
`FastMCP("splunkgate-mcp")`) AND `server.list_tools()` (async). The official `mcp` SDK's
FastMCP does not expose `server.list_tools()` as an async coroutine returning Tool
objects you can iterate with `.name` and `.outputSchema` — its public surface is
`@server.tool()` decorators and an internal `_tool_manager`. The shell verification
block `tools = asyncio.run(server.list_tools())` will TypeError on a recent SDK.

Same issue in mcp-02 line 90, mcp-03 line 89, mcp-04 line 93, mcp-05 line 100 — all four
do `asyncio.run(server.list_tools())` and treat results as Tool objects with `.name`
and `.outputSchema` attrs.

**Suggested fix.** Either:

(a) Pin and cite the exact mcp SDK version in mcp-01 pyproject (e.g. `mcp>=1.5.0`)
and verify against its actual `FastMCP._mcp_server.list_tools()` shape, OR

(b) Add a thin wrapper `splunkgate_mcp.server.list_tools_for_test()` to the file mod map
that returns `list[ToolRecord]` from a local registry the `register_tool(...)` helper
populates. Tests use the wrapper; production code stays SDK-native.

I recommend (b) — it makes the registry helper from mcp-01 line 25 the source of truth
for tests, decouples test code from SDK internals, and is verifiable today.

### B-C-04 — story-mcp-05 — AuditReport.aggregate field is dict but the type declaration shows raw `dict` without value typing

**Location:** mcp-05 line 23.

**Problem.** `AuditReport.aggregate: dict` (no type parameters). Pydantic with strict
mypy in `splunkgate_core` (per architecture.md line 181 — strict required) treats bare `dict`
as `dict[Any, Any]` and architecture.md line 355 explicitly bans `Any` annotations in
splunkgate_core. Also AC at lines 27/150 expects `splunkgate.audit.event_count` as integer attribute
on the OTel event, but the architecture.md §"API schemas" doesn't list `splunkgate.audit.*`
as a defined attribute — this would be a NEW custom attribute on a load-bearing surface,
which deserves explicit ADR mention.

**Suggested fix.**
- Change `aggregate: dict` → `aggregate: dict[str, int | float | str]` (covers stats
  count by X return shapes) OR `aggregate: Mapping[str, str | int | float]` with a
  one-line comment justifying the freeform shape.
- Add a one-line ADR note in the story: "Per architecture.md ADR-004, MCP tools emit
  via `splunkgate_core.otel` — this story introduces the `splunkgate.audit.event_count` span
  attribute as a one-off; future ADR may codify it as `splunkgate.audit.*` namespace."

### B-C-05 — story-mw-07 — support_agent.py 30-LOC counting rule is checkable but the example skeleton EXCEEDS 30 lines

**Location:** mw-07 lines 179-210 (the skeleton in Notes).

**Problem.** Counted with the AC's exact `grep -v -E '^\s*(#|$|from |import )'`:

```
async def main() -> None:
    service = connect(host=os.environ["SPLUNKGATE_SPLUNK_HOST"], ...)
    model = OpenAIModel(model="gpt-4o", api_key=os.environ["OPENAI_API_KEY"], base_url="...")
    profile = "financial_services"
    agent = Agent(
        model=model,
        system_prompt="You are a Splunk support agent.",
        service=service,
        tool_middleware=[SafetyToolMiddleware(profile=profile)],
        model_middleware=[SafetyModelMiddleware(profile=profile)],
        subagent_middleware=[SafetySubagentMiddleware(profile=profile)],
        agent_middleware=[SafetyAgentMiddleware(profile=profile)],
    )
    async with agent:
        response = await agent.invoke_with_data(
            "Summarize this customer record.",
            {"name": "Jane Doe", "card_last4": "1234"},
        )
    print(response)
if __name__ == "__main__":
    asyncio.run(main())
```

Body lines (excluding `from`/`import`/blank/comment): 22. That LOOKS OK — BUT the AC
grep at line 72 strips `from ` and `import ` at start-of-line; it does NOT strip the
inner `if __name__` block lines (3 lines) or the dictionary-literal continuation lines.
Actual count with the AC grep = 22 lines from `async def main` through `print(response)`
+ 3 lines for `if __name__` block = 25 lines. **OK — passes.** Non-issue. Move to
minor (B-M-08).

Actually re-counting more carefully: the AC's `wc -l` runs after `grep -v`, which counts
NON-blank lines. Lines like `        response = await agent.invoke_with_data(` and the
two continuation lines all count individually. Recount: 24 statement-equivalent lines.
**Confirmed passes 30-LOC budget.** Demoting to non-issue.

### B-C-06 — story-mcp-02 — `splunkgate_judges.splunklib_security_fallback.detect_injection` invented module

**Location:** mcp-02 line 24, 132.

**Problem.** No EPIC-04 or EPIC-05 story creates a module named
`splunkgate_judges.splunklib_security_fallback`. The actual splunklib import path per
context/02-agent-frameworks/06-splunklib-ai-deep-read.md line 127 is
`from splunklib.ai.security import detect_injection` (or
`from splunklib.ai import detect_injection`). The mw-03 story-mw-03 creates a thin shim
at `packages/splunkgate_mw/src/splunkgate_mw/_first_pass.py` — but that's in `splunkgate_mw`, not
`splunkgate_judges`, and is not exported.

**Suggested fix.** Either:
(a) Add to mcp-02 file mod map: a thin re-export shim at
`packages/splunkgate_judges/src/splunkgate_judges/splunklib_security_fallback.py` that does
`from splunklib.ai.security import detect_injection`, OR
(b) Change mcp-02 line 24 to import directly:
`from splunklib.ai.security import detect_injection`.

(b) is simpler. Use that.

### B-C-07 — Cross-story — `defenseclaw_backend` module is imported by 3 stories but no story creates it

**Location:** mw-02 line 23 (`splunkgate_judges.defenseclaw_backend.evaluate_tool_call`),
mw-05 line 114 (`splunkgate_judges.defenseclaw_backend.evaluate_subagent_call`),
mcp-03 lines 23/144 (`splunkgate_judges.defenseclaw_backend.evaluate_tool_call`).

**Problem.** Three Surface 1/Surface 2 stories depend on a `defenseclaw_backend` Python
module that no EPIC-04, EPIC-05, or EPIC-08 story creates. EPIC-08 (dc-01/02/03) ships
config YAML, an upstream PR plan, and a LangGraph example — NONE of them ship a Python
`splunkgate_judges.defenseclaw_backend` module. mw-02 line 117 says "treat that import as
the contract; respx fixture can stand in if EPIC-08 hasn't landed yet (mark with TODO +
issue link)" — this is a known gap, but unresolved.

**Suggested fix.** Add a new EPIC-08 story (or fold into dc-01):
- `story-dc-01b-defenseclaw-python-shim.md` — NEW story creating
  `packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` with the two API
  functions `evaluate_tool_call(name, args) -> RuleHit | None` and
  `evaluate_subagent_call(name, input) -> RuleHit | None`. Implementation can wrap the
  small Python-side subset of rules (regex patterns ported from DefenseClaw's
  `policies/guardrail/default/rules/*.yaml`); the FULL rule pack lives in Go in
  DefenseClaw upstream — we only need the in-process subset for tests + the cheap path
  inside `splunkgate_mw` and `splunkgate_mcp`.

Update dependency arrows in `sprint-status.yaml`: mw-02, mw-05, mcp-03 should depend on
the new dc-01b. Add the story to dispatch_queue in epics.md.

### B-C-08 — story-dc-02 — Tests grep `^\`\`\`diff` with quadruple-escape; will not parse

**Location:** dc-02 acceptance criteria line 59 and shell verification line 104.

**Problem.** The literal in the AC block is:
```
`awk '/^\\\`\\\`\\\`diff/,/^\\\`\\\`\\\`$/' integrations/defenseclaw/upstream-pr-notes.md | wc -l`
```

That awk pattern uses backslash-escape-backslash-tick — but awk regex doesn't escape
backticks at all, so `\` then `\` then `` ` `` is interpreted as a stray backslash plus
a literal backtick. The pattern needs to be `/^\`\`\`diff/` — but the BDD format
wrapping that command in backticks-then-markdown means the visible escaping is doubled
once more for the BDD code block, fine, but the shell verification block on line 104
removes one level of escaping and produces `awk '/^\`\`\`diff/,/^\`\`\`$/' ...` which is
still ambiguous because backticks inside single-quotes interact with shell parsing
differently depending on the shell. On zsh (the host shell), the command may fail with
"unmatched `".

**Suggested fix.** Replace the awk with a Python one-liner that doesn't have shell-quoting
risk:

```bash
diff_blocks=$(uv run python -c "
import re, pathlib
src = pathlib.Path('integrations/defenseclaw/upstream-pr-notes.md').read_text()
blocks = re.findall(r'^\`\`\`diff\n.*?\n\`\`\`$', src, re.M | re.S)
total = sum(b.count('\n') + 1 for b in blocks)
print(total)
")
if [ "$diff_blocks" -lt 20 ]; then echo "diff blocks too small: $diff_blocks"; exit 1; fi
```

Update the AC line 59 similarly.

---

## Minor findings

### B-M-01 — story-foundsec-01 — `verify_tls` env-var escape hatch wires up TWO things

**Location:** foundsec-01 line 124.

`SPLUNKGATE_DEV_INSECURE_TLS=1` is described as overriding `verify_tls=False`, but the
constructor takes `verify_tls: bool = True` and the BDD at line 52 says "constructed
with verify_tls=False → 1 warning event". The relationship between the env var and the
constructor arg isn't fully specified — if `verify_tls=True` (default) is passed but
the env var is also set, what happens? Spec it: env var is a NO-OP unless
`verify_tls=False` was explicitly passed.

### B-M-02 — story-foundsec-02 — escaping check uses fragile chr() codepath

**Location:** foundsec-02 lines 117-130 (shell verification block).

The string `assert '\\\\\"' in between_prompt_and_provider or chr(92)+chr(34) in
between_prompt_and_provider` is checking for `\"` (escaped double-quote). The expression
`'\\\\\"' ` in a Python single-quoted string literal embedded inside a bash heredoc
expands to `\\"` after 4 levels of escape, which is `\\` followed by `"` not `\"`.
Either intentionally check for `\\` + `"` (double backslash escape), or use the simpler
`r'\"'` form. Verify the intended escape semantics before locking the test.

### B-M-03 — story-foundsec-02 — provider= warning dedupe-via-module-level-flag isn't process-safe under tests

**Location:** foundsec-02 lines 64-65.

"dedupe via module-level flag" — fine for production but pytest may load the module
multiple times across fixtures, and the test at line 65 ("exactly 1 warning per process")
will flake. Use a `_warning_lock = threading.Lock()` + a `_warned_once: bool` flag
inside the module, and reset it in a `conftest.py` fixture for the FoundationSec tests.

### B-M-04 — story-foundsec-03 — vocabulary check is duplicated and the 8-of-14 vs. 4-of-14 bound is inconsistent

**Location:** foundsec-03 line 23 says vocabulary set MUST include "at least 8 of"
14 terms. AC line 44 says "at least 4 distinct strings". Shell verification line 120
says `hits >= 4`. The file mod map (line 23) says ≥ 8; the AC says ≥ 4. Pick one.

### B-M-05 — story-mw-01 — `__all__` claim missing from spec

**Location:** mw-01 AC line 50 asserts `splunkgate_mw.__all__` contains exactly 6 names, but
file mod map line 24 doesn't say `__init__.py` must declare `__all__`. Coding agent may
omit it and the AC will fail with `AttributeError: module 'splunkgate_mw' has no attribute
'__all__'`. Add to file mod map: "`__init__.py` declares `__all__ = [...]` with exactly
the 6 listed names."

### B-M-06 — story-mw-02 — `surface="mw_tool"` literal is asserted but no story defines it as canonical

**Location:** mw-02 AC line 51 asserts `splunkgate.surface="mw_tool"`. mw-05 line 23 asserts
`surface="mw_subagent"`. mw-06 line 23 asserts `surface="mw_agent"`. mw-03/04 use
`surface="mw_model"`. These four literals are load-bearing for Surface 4 dashboards but
aren't declared as the canonical set in any architecture.md surface enum. Risk: a
typo in one story (e.g. `surface="mw_tools"` plural) will silently break the dashboard.

**Suggested fix.** Add to story-core-01 (or core-02) file mod map: a
`splunkgate_core.surfaces` module with `class Surface(str, Enum): MW_TOOL = "mw_tool"; ...`
and import the enum in every middleware/MCP story instead of using string literals.

### B-M-07 — story-mw-02 — `from_env()` factory pattern referenced but not specified for AI Defense client

**Location:** mw-02 line 118 says "AI Defense client `splunkgate_judges.ai_defense.inspect`
defaults to mock=True per ADR-006". No ADR-006 in the architecture.md I read. There is
ADR-005 (sourcetype), ADR-004 (own MCP), ADR-002 (monorepo), ADR-003 (Foundation-Sec
explainer-only), ADR-010 (cheap-first-pass). Verify ADR-006 exists or remove the
citation.

### B-M-08 — story-mw-07 — support_agent.py example skeleton uses `OpenAIModel` and `connect` shapes that may not match splunklib.ai 3.0.0

**Location:** mw-07 lines 181-210. `OpenAIModel(model="gpt-4o", api_key=..., base_url=...)`
constructor isn't verified against splunklib.ai 3.0.0's actual model constructor. The
context note at line 212 says `Agent` is an AsyncContextManager (verified) and
`invoke_with_data` exists (verified at `agent.py:296-311`). But the example uses
`splunklib.client.connect(...)` synchronously inside an async main — that's fine because
`connect` is sync, but the result `service` is passed to `Agent(service=service)`.
Verify Agent's actual constructor signature against
`context/02-agent-frameworks/06-splunklib-ai-deep-read.md` before locking the example.

### B-M-09 — story-mcp-01 — Origin header rejection BDD is unverifiable in-process

**Location:** mcp-01 AC lines 62-64.

"Given HTTP transport bound to 127.0.0.1, when POST with `Origin: https://attacker.example`,
then return 403." This is a network-level assertion; the AC needs to spell out the test
mechanism (TestClient via httpx, or actual http.server bound to ephemeral port). Without
the harness named, an agent will write a test that stubs the Origin check at the function
level and the actual binding behavior never gets verified.

### B-M-10 — story-mcp-02 — VerdictLabel cited but capitalization conflicts with architecture.md

**Location:** mcp-02 line 14 (verdict labels ALLOW / BLOCK / MODIFY / REVIEW) vs.
architecture.md line 261 `class VerdictLabel(str, Enum):` (not shown what the values are).
mcp-02 line 49 asserts `verdict.verdict.value in {'ALLOW','BLOCK','MODIFY','REVIEW'}` —
mw-02 line 23 uses `BLOCK`/`MODIFY`/`ALLOW` (no REVIEW). Is `REVIEW` a real label?
mw-04 doesn't mention it. mcp-03 line 14 mentions REVIEW. dc-* doesn't.

**Suggested fix.** Lock the label set in core-01 explicitly. The audit can't verify
which 3 or 4 labels are canonical without reading core-01.

### B-M-11 — story-mcp-03 — `Verdict.modifications` field type is `dict | None` per architecture but test asserts "modifications field is omitted (not null)"

**Location:** mcp-03 line 25 ("modifications field is omitted (not null) on non-MODIFY
verdicts"). Pydantic's default JSON serialization for `modifications: dict | None = None`
includes the field as `null`, NOT omit it. To omit, the field needs
`Field(default=None, exclude=...)` semantics or per-call `model_dump(exclude_none=True)`.
Spec the serialization mode.

### B-M-12 — story-mcp-04 — Redaction tokens hardcoded but rule-set includes "Code Detection" and others

**Location:** mcp-04 line 147 says verbatim tokens are `[REDACTED:PII]`,
`[REDACTED:PHI]`, `[REDACTED:PCI]`. But the architecture rule catalog (per
context/07-cisco-stack/01-ai-defense-deep.md line 171 reference in mw-07) has 11 rules
total — what's the redaction token for Code Detection? Sensitive Data? Either restrict
the tool to the 3 listed rules (consistent with AC's profile mapping at line 142) OR
extend the redaction token set. Currently inconsistent: rules_enabled at default is
`["PII"]` but the tool's TC also covers PHI/PCI per AC line 53/57.

### B-M-13 — story-mcp-05 — SPL injection allowlist for `eval_dimensions` includes "rules" and "classifications" but SPL `stats count by rules` does NOT work on a list-typed field

**Location:** mcp-05 line 147 ("Validate against a strict allowlist: `{'verdict',
'severity', 'surface', 'rules', 'classifications', ...}`").

`rules` in the Verdict schema is `list[RuleHit]`; SPL `stats count by rules` would
operate on the multivalued field and produce one row per rule entry — that may or may
not be intended. Spec the expected aggregate semantics or drop those two from the
allowlist.

### B-M-14 — story-mcp-06 — claim "Splunk's MCP Server docs use mcp-remote" needs verification

**Location:** mcp-06 lines 23, 151. The story says "Use Splunk's CiscoDevNet-README
example as the structural template" — the prior context file
`context/06-splunk-ai-stack/03-splunk-mcp-server.md` is cited but I didn't independently
verify the mcp-remote pattern is documented there. If Splunk's README uses a different
bridge (e.g., `streamable-http` direct in Claude Desktop), our example would diverge
from the structural template our own spec promised to mirror. Confirm before locking.

### B-M-15 — story-dc-01 — `mock_splunk_hec.py` is annotated as "§14 carve-out" and the file mod map says ≤ 80 LOC, but the §14 grep at AC line 69 only excludes `--include` markdown/yaml — the Python file IS scanned by the grep in shell verification line 126 but the file mod map ALREADY mentions "mock" in the filename.

**Location:** dc-01 line 26 vs. line 126.

`grep -rE "(mock|fake|dummy|hardcoded|simulated)" integrations/defenseclaw/README.md
integrations/defenseclaw/examples/defenseclaw.yaml integrations/defenseclaw/examples/docker-compose.yaml`
— actually only checks 3 specific files, so `mock_splunk_hec.py` is excluded. OK.
BUT: the README contains an architecture line that mentions "mock Splunk HEC" — verify
the README doesn't trip the §14 grep at line 126. (Skim: line 126 only checks
README.md + the two YAMLs.) Add a clarifying note: "README contains the literal word
`mock` in describing the test harness — the AC grep at line 69 ONLY scans `*.md` +
`*.yaml`, so this is covered. However, the §14 grep convention typically excludes lines
with `# §14 CARVE-OUT` — make sure the README's mention is in a fenced code block or
clearly attributed."

### B-M-16 — story-dc-02 — Tests use literal awk patterns inside BDD blocks; same shell-quoting fragility as B-C-08

**Location:** dc-02 lines 59, 104. Already covered by B-C-08 — flagging once more
because the test for "diff blocks present" is THE acceptance gate for this story being
"done", and that gate is currently structurally broken.

### B-M-17 — story-dc-03 — `mock_llm.py` and the §14 carve-out exclusion in tests

**Location:** dc-03 line 78. The §14 grep at line 79 only checks `agent.py`, `README.md`,
`defenseclaw-config.yaml` — `mock_llm.py` not in list, fine. But the README at line 23
says "the architecture line: `LangGraph agent → DefenseClaw proxy (proxy.go, 4430 LOC)
→ LLM upstream + SplunkGate HEC sink`" — that's fine. Just confirm the agent.py file does
not contain the word "mock" anywhere (the §14 grep on line 79 would fail). The agent
uses `SPLUNKGATE_LLM_BASE_URL` env var — should be safe.

---

## Non-issues (reviewed and OK)

- **NI-01 — story-foundsec-* triple-confirms Foundation-Sec as EXPLAINER only.** Every
  notes block ends with the EXPLAINER-only assertion + citation. mw-04 line 115
  re-asserts it via ADR-003. mcp-* doesn't touch Foundation-Sec for classification.
  This is the cleanest cross-story consistency in the batch.

- **NI-02 — story-mw-* uses the 4 distinct middleware kwargs.** mw-01 line 130 cites
  the deep-read explicitly; mw-07 line 170 re-cites; mw-01 line 131 specifically calls
  out the before_*/after_* hooks as NOT re-exported. Architecture is correct.

- **NI-03 — story-mcp-* uses official `mcp` SDK + protocol `2025-11-25`.** mcp-01 line
  141 explicitly says do NOT use `2025-03-26`. mcp-06 line 148 re-asserts. mcp-01 AC
  line 60 asserts the version literal. Clean.

- **NI-04 — story-dc-* cites DefenseClaw line counts (600 + 4430) correctly.** dc-01
  line 138, dc-02 line 137, dc-03 line 163. All three pin commit `e1cb4d93` and credit
  Apache-2.0. Upstream PR plan in dc-02 is markdown-only, no Go dump in repo. dc-03's
  LangGraph example is the cleanest demonstration of the "any agent any framework"
  pitch.

---

## Special-check matrix (per-batch verified claims)

| Check | Status |
|---|---|
| EPIC-05: Foundation-Sec positioned as EXPLAINER only | PASS |
| EPIC-05: `provider=` value flagged as unverified + env var override | PASS |
| EPIC-05: SPL-injection escaping present in explanation prompt | PASS |
| EPIC-05: no F1 numbers claimed for Foundation-Sec | PASS |
| EPIC-06: 4 distinct middleware kwargs (not before/after × model/tool) | PASS |
| EPIC-06: 9-regex cheap first-pass documented as keeper, not replacement | PASS |
| EPIC-06: LangChain v1 transitive dep acknowledged | PASS (mw-01 line 133) |
| EPIC-06: AgentLimits `max_structured_output_retires` typo preserved | PASS (mw-04 line 118; mw-06 line 131) |
| EPIC-06: splunklib.ai 3.0.0 May 12 2026 PyPI date correct | PASS (mw-01 line 132) |
| EPIC-06: mw-03/mw-04 split structurally works | **FAIL** (see B-C-02) |
| EPIC-06: support_agent.py ≤ 30 lines body | PASS (recounted — ~24 lines) |
| EPIC-07: official `mcp` Python SDK | PASS (mcp-01 line 142 explicitly bans flask/fastapi) |
| EPIC-07: MCP protocol 2025-11-25 pinned | PASS |
| EPIC-07: structuredContent + outputSchema used | PASS |
| EPIC-07: tool names use `splunkgate_` prefix (not splunk_/saia_) | PASS — all 4 tools |
| EPIC-07: Splunk MCP Server closed-source coexistence acknowledged | PASS (cited 6 times) |
| EPIC-07: MCP sub-convention attrs co-emit with gen_ai.evaluation.result | PARTIAL (mcp-01 spec'd; mcp-02/03/04/05 only assert `splunkgate.surface` not `mcp.method.name` — see B-M-XX) |
| EPIC-07: `AuditReport` added to `splunkgate_core` | PASS (mcp-05 line 23) |
| EPIC-08: DefenseClaw line counts (600 + 4430) cited correctly | PASS |
| EPIC-08: Apache-2.0 acknowledged | PASS |
| EPIC-08: upstream PR is markdown + branch ref, NOT Go dump in repo | PASS (dc-02 line 21, line 31, line 136) |
| EPIC-08: LangGraph example demonstrates any-framework coverage | PASS |
| EPIC-08: defenseclaw_backend Python shim wired | **FAIL** (see B-C-07) |

---

## Per-story matrix

| Story ID | Format | BDD | File-map | Citations | Critical findings |
|---|---|---|---|---|---|
| story-foundsec-01 | OK | OK | OK | OK | None |
| story-foundsec-02 | OK | OK | OK | OK | B-M-02 (escape check), B-M-03 (dedupe) |
| story-foundsec-03 | OK | OK | OK | OK | B-M-04 (vocab bound inconsistent) |
| story-mw-01 | OK | OK | OK | strong | B-M-05 (`__all__` missing) |
| story-mw-02 | OK | OK | OK | strong | B-C-07 (defenseclaw_backend), B-M-07 (ADR-006 missing) |
| story-mw-03 | OK | OK | OK | strong | B-C-02 (split structure) |
| story-mw-04 | OK | OK | OK | strong | B-C-01 (Foundation-Sec contract), B-C-02 (split) |
| story-mw-05 | OK | OK | OK | strong | B-C-07 (defenseclaw_backend) |
| story-mw-06 | OK | OK | OK | strong | None critical |
| story-mw-07 | OK | OK | OK | strong | B-M-08 (OpenAIModel constructor unverified) |
| story-mcp-01 | OK | OK | OK | strong | B-C-03 (FastMCP test contract) |
| story-mcp-02 | OK | OK | OK | strong | B-C-03 (test harness), B-C-06 (invented module), B-M-10 (label set) |
| story-mcp-03 | OK | OK | OK | strong | B-C-03, B-C-07, B-M-11 (modifications serialization) |
| story-mcp-04 | OK | OK | OK | strong | B-C-03, B-M-12 (redaction tokens incomplete) |
| story-mcp-05 | OK | OK | OK | strong | B-C-01 (foundation_sec API), B-C-04 (dict typing), B-M-13 (SPL stats by rules) |
| story-mcp-06 | OK | OK | OK | OK | B-M-14 (Splunk README structural template unverified) |
| story-dc-01 | OK | OK | OK | strong | None critical (citations excellent) |
| story-dc-02 | OK | OK | OK | strong | B-C-08 (awk escape pattern), B-M-16 (same) |
| story-dc-03 | OK | OK | OK | strong | None critical |

---

## Recommended fix priority (for orchestrator)

Block dispatch until fixed:

1. **B-C-07** (defenseclaw_backend module missing) — affects mw-02, mw-05, mcp-03. The
   coding agents for these three stories will hit an `ImportError` immediately.
2. **B-C-01** (Foundation-Sec contract mismatch) — affects mw-04 and mcp-05. The
   coding agent will write code that doesn't compile against the EPIC-05 deliverable.
3. **B-C-02** (mw-03/mw-04 split structure) — affects mw-03 and mw-04. The append-at-anchor
   pattern needs a clear seam contract.
4. **B-C-03** (FastMCP test contract) — affects all 5 mcp-* stories. The
   `server.list_tools()` test pattern doesn't work against the real SDK.
5. **B-C-06** (mcp-02 invented module) — simple textual fix.
6. **B-C-08** (dc-02 awk escape) — simple textual fix.

Can proceed in parallel with fixes:
- All minor findings (B-M-01 through B-M-17) can be addressed via small spec edits
  during dispatch.

---

## Author's note

This batch is the cleanest spec-citation work I've seen in the audit so far. Every
load-bearing claim has a `context/` cite, the Foundation-Sec EXPLAINER-only framing is
triple-confirmed, the MCP `2025-11-25` pinning is explicit and consistent, and the
DefenseClaw 600/4430 line counts are cited at three independent points across the three
DC stories. The structural problems (B-C-01, B-C-02, B-C-07) are all "the integration
seam between epics isn't fully wired" — fixable in a single ~30-minute pass before
orchestrator dispatch.

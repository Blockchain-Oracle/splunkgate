# SplunkGate MCP Server — Phase A0 design (2026-06-09)

Locked design for building Surface 2 (`splunkgate_mcp`) to ship-quality before Jun 15. Captures decisions made in the design conversation + 6 revisions that surfaced during pre-lock verification against the codebase.

## Context

`packages/splunkgate_mcp/` is a 3-line empty stub today. Per ADR-013 (2026-06-05), v1 MCP scope was narrowed and `story-mcp-04` + `story-mcp-05` were DEFERRED. **This design reopens both** — building all 4 tools strengthens the Best MCP $1K bonus pitch AND matches story-mcp-06's existing docs which already enumerate 4 tools.

The design does not introduce new architecture; the 4 story specs (mcp-01 through mcp-06) remain the contract. This doc captures:
- Decisions made during this brainstorming conversation
- 6 revisions to original story specs caught during pre-lock verification
- PR sequence + dependency graph
- Sprint-status + ADR-013 addendum updates this triggers

## Scope (4 tools, 6 PRs)

| Story | Tool | Surface | OutputSchema | Status flip |
|---|---|---|---|---|
| mcp-01 | (skeleton — `_ping` only) | — | Verdict | PENDING → IN_PROGRESS |
| mcp-02 | `splunkgate_score_prompt_injection` | `mcp_score` | `Verdict` | PENDING → IN_PROGRESS |
| mcp-03 | `splunkgate_judge_tool_call` | `mcp_judge_tool` | `Verdict` | PENDING → IN_PROGRESS |
| mcp-04 | `splunkgate_check_output_leak` | `mcp_check_output` | `Verdict` | **DEFERRED → PENDING** (reopened) |
| mcp-05 | `splunkgate_audit_trace` | `mcp_audit` | `AuditReport` | **DEFERRED → PENDING** (reopened) |
| mcp-06 | (docs — coexistence + integration) | — | — | PENDING → IN_PROGRESS |

## Architecture (locked by story specs)

- **SDK**: official `mcp` Python SDK (`mcp[cli]`). `FastMCP` server pattern. Banned: flask, django, fastapi.
- **Protocol version**: `2025-11-25` (Stable).
- **Transports**: `stdio` (default per spec); Streamable HTTP env-toggled via `SPLUNKGATE_MCP_TRANSPORT=http`. HTTP binds `127.0.0.1` only + Origin header validation (DNS-rebinding mitigation per MCP spec).
- **Tool registration**: `register_tool(name, fn, input_schema, output_schema, description)` populates internal `_REGISTERED_TOOLS: dict[str, RegisteredTool]`. The dict IS the source of truth.
- **Test enumeration**: `_test_helpers.list_tools_for_test()` reads `_REGISTERED_TOOLS` directly. FastMCP's async protocol surface (`tools/list`) is NOT a sync registry — tests must use the helper, not `asyncio.run(server.list_tools())`.
- **OTel**: every tool invocation wraps in `mcp.server` span (SERVER kind) with `mcp.method.name="tools/call"`, `mcp.session.id`, `mcp.protocol.version="2025-11-25"`. Emits `gen_ai.evaluation.result` event via `splunkgate_core.otel` (reused, NOT re-implemented).
- **Error reporting**: in-band `isError: true` on tool result, NOT JSON-RPC errors (MCP spec).
- **Sourcetype**: mcp-05's SPL uses `cisco_ai_defense:splunkgate_verdict` verbatim (ADR-005).

## Revisions vs original story specs (caught during pre-lock verification)

These 6 revisions resolve real spec/codebase gaps. Each PR's commit message must cite the relevant revision so reviewers see the rationale:

1. **mcp-05: `AuditReport.aggregate` is `dict[str, object]`, NOT `dict[str, Any]`**
   *Reason*: CLAUDE.md hard rule — no `Any` in `splunkgate_core` or `splunkgate_judges`. Mirrors the existing `Verdict.modifications: dict[str, object] | None` pattern. The `repr()`-or-`isinstance` access pattern at consumers stays the same; only the type annotation changes.

2. **mcp-05: Splunk REST search auth uses USER + PASSWORD, NOT HEC token**
   *Reason*: `SPLUNKGATE_SPLUNK_HEC_TOKEN` is write-only for HEC indexing — wrong scope for `/services/search/jobs`. The env already exposes `SPLUNKGATE_SPLUNK_HOST` + `SPLUNKGATE_SPLUNK_USER` + `SPLUNKGATE_SPLUNK_PASSWORD` (verified). The Splunk REST client constructs an `httpx.BasicAuth(user, password)` and POSTs to `/services/search/jobs?output_mode=json`.

3. **mcp-05: `SplunkSearchClient` lives in `splunkgate_judges/splunk_search.py`, NOT `splunkgate_judges/foundation_sec.py`**
   *Reason*: `foundation_sec` module is DEFERRED per ADR-013 (Hosted Models access unverified). The Splunk REST abstraction is independently useful — extract it cleanly. Future `story-foundsec-02` (Foundation-Sec `| ai` SPL prompt, when undeferred) can import from `splunk_search` for its REST search needs. Updates `story-mcp-05`'s file modification map to point at the new path.
   *Ownership*: `SplunkSearchClient` constructs its own `httpx.AsyncClient` inside `from_env()` and owns its lifecycle. Callers call `await client.aclose()` to release the connection pool; `async with SplunkSearchClient.from_env() as client:` is the recommended pattern in tests and `__main__`. Disambiguates the API for downstream consumers (mcp-05 audit_trace + future foundsec-02 SPL caller).

4. **mcp-06 docs: Splunk MCP Server is on Splunkbase app 7931, NOT "closed-source"**
   *Reason*: ADR-004a (2026-06-05 correction). The CiscoDevNet repo was README+LICENSE at research time, but Splunk LLC published the real app to Splunkbase (verified live Playwright probe 2026-06-05; 13,990 downloads). Coexistence demo now references **three** real Splunkbase apps in one MCP client config: 7931 (Splunk MCP) + 7245 (SAIA) + ours (SplunkGate). This is the load-bearing artifact for the Best MCP $1K bonus narrative.

5. **All tools: tests use `respx` + `splunkgate_judges.ai_defense_mock` fixtures per ADR-006**
   *Reason*: AI Defense mocks default to `mock=True` per CLAUDE.md hard rule. The existing `ai_defense_mock` module from EPIC-04 already wires respx — reuse it. No duplicate mock infrastructure in `splunkgate_mcp`.

6. **mcp-05: TLS handling uses `SPLUNKGATE_DEV_INSECURE_TLS=1` opt-in with WARN log**
   *Reason*: Same pattern as `splunkgate_core/otel_hec_exporter.py:198` — opt-in env var for self-signed certs (local Docker Splunk in dev), production defaults to `verify=True`. NOT a violation of CLAUDE.md "no `verify=False` in production HTTP" because it's the documented escape hatch with telemetry visibility (WARN log).

## New backend modules (bundled with first consumer)

Per Abu's decisions, two new modules ship inside the consuming MCP PR (not as standalone stories):

1. **`packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py`** — in mcp-03 PR (**absorbs `story-judges-06`**)
   *Ownership note*: This file path is explicitly attributed to `story-judges-06-defenseclaw-python-shim` (PENDING) in `docs/architecture.md:86` and `docs/sprint-status.yaml`. The mcp-03 bundling is not an end-run around judges-06 — it IS judges-06, shipped inside the first PR that consumes it. Sprint-status flips both `story-judges-06` and `story-mcp-03` to COMPLETE when the mcp-03 PR merges. Architecture.md line 86's owner annotation stays accurate.
   *Dependency note*: `story-judges-06` declares a dep on `story-dc-01` (DefenseClaw config-delta docs, PENDING). For the mcp-03 PR we forward-declare the regex subset without waiting on dc-01's documentation prose; the regexes are the load-bearing artifact, not the docs. dc-01 lands separately and references back to this implementation.
   *Purpose*: Cheap-first-pass classifier for tool-call arg sets. Port the DefenseClaw rule-pack subset (regex patterns for `shell_exec`, `rm -rf`, base64 payload, US SSN, common PII patterns).
   *API*: `async def evaluate_tool_call(tool_name: str, tool_args: dict[str, object]) -> RuleHit | None`
   *Source*: regex literals embedded in module (no fixture file dep on EPIC-08). If EPIC-08's `defenseclaw_rules.json` lands later, refactor reads it.
   *Test surface*: ≥ 8 behavioral tests in `tests/test_defenseclaw_backend.py` alongside the mcp-03 PR's tool tests.
   *LOC budget*: ≤ 200 (mostly regex declarations + matcher loop).

2. **`packages/splunkgate_judges/src/splunkgate_judges/splunk_search.py`** — in mcp-05 PR
   *Purpose*: Splunk REST search abstraction for SPL execution against `/services/search/jobs`. Used by mcp-05 audit_trace now; future foundsec-01 + S4 verdict-history reads can import from here.
   *API*: `class SplunkSearchClient: async def from_env() -> Self; async def submit_search(spl: str) -> list[dict[str, object]]; async def aclose() -> None`
   *Auth*: `httpx.BasicAuth` from `SPLUNKGATE_SPLUNK_USER` + `SPLUNKGATE_SPLUNK_PASSWORD`. Host from `SPLUNKGATE_SPLUNK_HOST`. TLS verify=True default; `SPLUNKGATE_DEV_INSECURE_TLS=1` opt-in with WARN log.
   *Test surface*: ≥ 10 behavioral tests in `tests/test_splunk_search.py` (respx for HTTP, valid/error/timeout paths).
   *LOC budget*: ≤ 250.

Plus one new core type:

3. **`packages/splunkgate_core/src/splunkgate_core/audit_report.py`** — in mcp-05 PR
   *Purpose*: Pydantic shape for mcp-05's `AuditReport` output. Shared between MCP tool and Surface 4 dashboards.
   *Shape*: `class AuditReport(BaseModel): trace_id: UUID; event_count: int; verdicts: list[Verdict]; first_seen: datetime; last_seen: datetime; surfaces_seen: list[str]; aggregate: dict[str, object]` *(note `object`, not `Any` — revision 1)*.
   *Test surface*: ≥ 6 behavioral tests in `tests/test_audit_report.py` (validation, JSON-schema export, round-trip).

## Dependency graph + PR sequence

```
mcp-01 (skeleton + _ping)
  │
  ├──> mcp-02 (score_prompt_injection)   [parallel with mcp-04]
  │      └─ uses splunkgate_judges.ai_defense (existing)
  │      └─ uses splunklib.ai.security.detect_injection (cheap first-pass)
  │
  ├──> mcp-04 (check_output_leak)        [parallel with mcp-02]
  │      └─ uses splunkgate_judges.ai_defense (existing)
  │
  ├──> mcp-03 (judge_tool_call + bundled defenseclaw_backend)
  │      └─ new: splunkgate_judges/defenseclaw_backend.py
  │
  └──> mcp-05 (audit_trace + bundled splunk_search + audit_report)
         └─ new: splunkgate_judges/splunk_search.py
         └─ new: splunkgate_core/audit_report.py

mcp-06 (docs — 4-tool integration + coexistence example with apps 7931/7245)
```

**Parallelism**: mcp-02 and mcp-04 land as parallel branches because they only depend on mcp-01 + the existing AI Defense client. Each gets its own PR + review fleet.

**PR sequence (6 PRs total)**: mcp-01 → (mcp-02 + mcp-04 in parallel) → mcp-03 → mcp-05 → mcp-06. Each PR ships at the same quality bar (full review fleet, live verification, no `--no-verify`). The sequence respects dependencies; total elapsed time is whatever quality requires, not a fixed-day allocation.

## Test pattern (locked by spec)

- **Tool enumeration**: `_test_helpers.list_tools_for_test()` (story-mcp-01 owns this).
- **Mocks**: `respx` for AI Defense + Splunk REST. Reuse `splunkgate_judges.ai_defense_mock` fixtures.
- **Test counts**: mcp-01 ≥ 10 tests; mcp-02/03/04/05 ≥ 12 each; defenseclaw_backend ≥ 8; splunk_search ≥ 10; audit_report ≥ 6.
- **OTel verification**: in-test exporter attached; assert exactly one `gen_ai.evaluation.result` event per tool call with correct `splunkgate.surface` attribute.
- **§14 grep clean**: `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/` returns empty for production code (tests carved out per §14).
- **400 LOC cap**: enforced per source file; pre-commit hook + PR review.

## Coexistence demo (mcp-06)

The Best MCP $1K bonus pitch hinges on this artifact. mcp-06 ships `docs/integrations/_examples/splunkgate-mcp-coexist-with-splunk.json` showing three MCP servers in one MCP client config block:

- `splunk-mcp-server` (Splunkbase app **7931**, 10 native `splunk_*` tools)
- `saia-mcp-server` (Splunkbase app **7245**, 4 `saia_*` tools)
- `splunkgate-mcp-server` (this surface, 4 `splunkgate_*` tools)

Three prefixes (`splunk_*` / `saia_*` / `splunkgate_*`) partition cleanly — no name collisions. mcp-06's README enumerates all 18 tools verbatim (10 + 4 + 4) so judges and developers see the partition.

## Per-PR review fleet (CLAUDE.md step 7)

Non-negotiable per `memory:feedback_pr_review_every_pr` + `memory:feedback_use_full_pr_review_toolkit`. Dispatch 2-4 specialists in parallel for each PR:

| PR | Reviewers |
|---|---|
| mcp-01 (skeleton) | code-reviewer + simplification-reviewer + security-reviewer |
| mcp-02 (score) | code-reviewer + simplification-reviewer + security-reviewer |
| mcp-03 (judge_tool_call + defenseclaw_backend) | code-reviewer + security-reviewer + silent-failure-hunter |
| mcp-04 (check_output_leak) | code-reviewer + security-reviewer + simplification-reviewer |
| mcp-05 (audit_trace + splunk_search + audit_report) | code-reviewer + security-reviewer + silent-failure-hunter (SPL injection + Splunk REST error paths) |
| mcp-06 (docs) | comment-analyzer + simplification-reviewer |

`security-reviewer` on every PR because MCP surface is internet-adjacent (HTTP transport, Origin header, SPL injection, basic auth handling).

## Sprint-status updates triggered by this design

1. **mcp-04**: DEFERRED → PENDING (reopened — see ADR-013 addendum below)
2. **mcp-05**: DEFERRED → PENDING (reopened — see ADR-013 addendum below)
3. **mcp-01, mcp-02, mcp-03**: PENDING → IN_PROGRESS (as each one's PR opens)
4. **mcp-06**: PENDING → IN_PROGRESS (after the 4 tool PRs land)
5. **judges-06** (defenseclaw_python_shim): PENDING → COMPLETE when mcp-03 PR merges (absorbed — see "New backend modules" section above)
6. **story-app-13** drift fix: PENDING → COMPLETE (PR #110 already merged 2026-06-08)

Commit message convention: `chore(sprint-status): flip <story-id> to <STATUS>`. Commit directly to `main` (no PR needed for status hygiene).

## ADR-013 addendum (to be appended to `docs/architecture.md`)

> **ADR-013a — mcp-04 + mcp-05 reopened (2026-06-09).** Original deferral reasoned (a) mcp-04 was redundant with S1 post-inference scan, (b) mcp-05 was redundant with S4 KV-store. Both arguments hold for cross-surface redundancy, but neither was the right reason to forfeit MCP-tool coverage on Surface 2 itself — every MCP client (Claude Desktop, Cursor, custom) needs ALL relevant tools exposed on the server it talks to, regardless of what exists on other surfaces. The 4-tool framing also matches story-mcp-06's existing docs (which enumerate all four verbatim) and strengthens the Best MCP $1K bonus pitch by giving the coexistence example real coverage. Reopening triggers two new module dependencies bundled with their consumers: `splunkgate_judges/defenseclaw_backend.py` (in mcp-03 PR) and `splunkgate_judges/splunk_search.py` + `splunkgate_core/audit_report.py` (in mcp-05 PR). No re-scoping of other surfaces.

## Open risks (surface honestly, not blockers)

1. **mcp-02 transitively depends on story-judges-05 (PENDING)** — judges-05 is the AI Defense e2e integration test (nightly eval). Not shown in the dependency graph above because it's not on the critical path. Mitigation: proceed with `respx` mocks per ADR-006. judges-05 is a quality gate for live AI Defense calls, not a blocker for mcp-02's correctness. (Caught in PR #114 review — added here for future readers.)

2. **`splunklib.ai.security.detect_injection` availability** — referenced by mcp-02 spec (and ADR-010). The mw package already imports `splunklib.ai.middleware` cleanly, so the package is installed at workspace level — but mcp-02 must declare the dep explicitly in `packages/splunkgate_mcp/pyproject.toml`. Verify during mcp-02 implementation.

3. **DefenseClaw rule-pack fidelity** — `defenseclaw_backend.py` ports a regex subset; the full Go-side rule-pack is richer. v1 covers shell injection + base64 + US SSN + common PII patterns. Honest signal surfaces in two places: (a) the `Verdict.explanation` string contains `"matched defenseclaw_regex subset; full rule-pack pending EPIC-08 integration."`, and (b) the `RuleHit.source` field is `"defenseclaw_regex"` (the Literal value already declared on RuleHit, per ADR-003). Downstream dashboards filter on `source="defenseclaw_regex"` and surface the "subset" caveat in the Verdict Inspector detail panel.

4. **Splunk REST search auth scope** — `SPLUNKGATE_SPLUNK_USER` is `sc_admin` per `.env`. mcp-05's `splunk_search.py` requires a role with `search_jobs_inspector` or equivalent capability. Verify by smoke test against local Docker container before merging mcp-05.

## Out of scope (consciously)

- `story-mcp-04`'s sensitivity profiles (default/fsi/hipaa/pubsec) drive `rules_enabled` lists to AI Defense — the profiles themselves are owned by `story-mw-07` (PENDING, Honest Signal in plan). mcp-04 uses the hardcoded mapping from its story spec (lines 143-147) without dynamic loading.
- Foundation-Sec explainer integration in `splunk_search.py` — out of scope (foundation_sec module is DEFERRED). The new module is purely the REST abstraction.
- Splunkbase publish for our MCP server — the Splunk MCP Server itself is on Splunkbase (7931); ours is GitHub-shipped + `pip install splunkgate-mcp`. Splunkbase shipping is a v2 story.
- `splunk_run_saved_search` overlap with mcp-05 — story-mcp-05 notes the overlap (Splunk's MCP exposes `splunk_run_saved_search`; our `splunkgate_audit_trace` does the same shape but with our sourcetype + trace_id filter baked in). The coexistence example surfaces both tools side-by-side for the developer to pick.

## Verification before locking design

The following were verified against the codebase (not the spec) during pre-lock pass:

- ✅ `Verdict.surface` Literal already includes all 4 mcp surfaces (`mcp_score`, `mcp_judge_tool`, `mcp_check_output`, `mcp_audit`)
- ✅ `Verdict.modifications: dict[str, object] | None` exists — `AuditReport.aggregate` follows the same pattern
- ✅ `AIDefenseClient.inspect_chat` is async, returns `InspectResponse`. All 4 tools await it.
- ✅ AI Defense rule names ("Prompt Injection", "PII", "PHI", "PCI") match `packages/splunkgate_judges/tests/test_ai_defense_types.py` fixtures verbatim
- ✅ `SPLUNKGATE_DEV_INSECURE_TLS` already wired in `splunkgate_core/otel_hec_exporter.py:198` with WARN log — same pattern reused
- ✅ `splunklib.ai.middleware` imported cleanly by `packages/splunkgate_mw/src/splunkgate_mw/_base.py` — module is workspace-available
- ✅ `.env` exposes `SPLUNKGATE_SPLUNK_USER` + `SPLUNKGATE_SPLUNK_PASSWORD` for REST search auth (not just HEC write token)
- ✅ Sourcetype `cisco_ai_defense:splunkgate_verdict` is what S4 dashboards filter on (verified during PR #113 work)

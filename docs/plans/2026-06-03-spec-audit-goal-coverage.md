# Spec Audit — Goal Alignment + Coverage Gaps

Auditor: goal + coverage
Date: 2026-06-03

## Summary

**4 critical gaps · 7 minor gaps · the rest confirmed-covered.**

The spec set delivers on the three PRD functional pillars (prompt injection / output leak / tool-call safety) end-to-end across the four surfaces, hits every demo-moment beat with a named story, and maps cleanly to each of the four judging criteria. The critical gaps are all in the "make the demo actually render" wiring: there is no story that ships the OTel-to-Splunk HEC bridge configuration, no story that owns the `scripts/emit_sample_verdict.py` synthetic-event emitter that two downstream stories assume exists, no story that runs a full end-to-end integration test from agent action → OTel → Splunk index → dashboard query, and no story that configures GitHub-side operational concerns (branch protection, repo secrets). All four are easy to add — each is a single story file in the existing structure.

## Critical coverage gaps (block submission or block demo)

- **G-C-01 — No story owns `scripts/emit_sample_verdict.py` (orphan synthetic event emitter referenced by two stories)**
  - Expected deliverable: a script that emits a deterministic set of sample `Verdict` events (covering all 4 surfaces, 11 rules, all severities) into Splunk via HEC, so dashboards have data to render during dev + demo recording.
  - Why no story covers it: `story-app-02` shell verification block 5 invokes `scripts/emit_sample_verdict.py` and the Notes section explicitly says "lives outside this story's file modification map; if it doesn't exist yet, gate the block on `[ -f scripts/emit_sample_verdict.py ]`". `story-app-10` shell loop step 2 invokes the same script and says "if the script doesn't exist yet, this story's `visual_loop.sh` should gracefully skip event emission". Both stories assume someone else will build it; no one does.
  - Impact: dashboards will load empty in the visual loop validation (story-app-10), and the demo recording (story-demo-01) has no way to populate the dashboard "live counters" beat 1 requires — beat 1 of PRD § Demo moment explicitly requires "live counters".
  - Suggested fix: add `story-app-13-emit-sample-verdict-script.md` under EPIC-09 with `depends_on: [story-core-02-otel-evaluation-event-emitter, story-app-02-props-transforms-for-splunkgate-verdict-sourcetype]`. Script emits ~500 events via HEC, parameterized via env vars (`SPLUNKGATE_SPLUNK_HEC_URL`, `SPLUNKGATE_SPLUNK_HEC_TOKEN`). Add as a dep of `story-app-10` and `story-demo-01`.

- **G-C-02 — No story wires the OTel → Splunk HEC export bridge (events emitted ≠ events landing in Splunk)**
  - Expected deliverable: an OTel exporter configuration that takes `gen_ai.evaluation.result` events emitted by `splunkgate_core.otel.emit_verdict_event()` and ships them to Splunk HEC with the right sourcetype, so the loop from agent → middleware → verdict → OTel → Splunk → dashboard actually closes.
  - Why no story covers it: `story-core-02` only wires `add_event()` against the current OTel span, terminating in an in-memory exporter for tests. No story configures `opentelemetry-exporter-splunk-hec`, `splunk_hec_logs_exporter`, an OTel Collector sidecar, or equivalent. The architecture.md § "OTel emission shape" says "The OTel pipeline lands these in Splunk via HEC; Splunk's `props.conf` parses them into the `cisco_ai_defense:splunkgate_verdict` sourcetype" — but no story builds the pipeline.
  - Impact: in a live run, events emit to OTel and disappear. The demo's beat 4 ("On the Splunk dashboard the counter ticks up") only works because story-app-10 / story-demo-01 inject synthetic events via the missing `emit_sample_verdict.py`. The architecture promise that "every surface lands every verdict as an OTel event in Splunk" is unverified end-to-end.
  - Suggested fix: add `story-core-05-otel-hec-exporter-config.md` under EPIC-03 with deliverables: `packages/splunkgate_core/src/splunkgate_core/otel_hec.py` (configures the HEC exporter; reads `SPLUNKGATE_SPLUNK_HEC_URL`, `SPLUNKGATE_SPLUNK_HEC_TOKEN`, `SPLUNKGATE_OTEL_EXPORT_MODE` envs), `docs/runbook/otel-pipeline.md` (operator doc on which OTel Collector receivers/processors/exporters to enable), and an integration test that posts a fake span and asserts the HTTP POST hits a respx-mocked HEC endpoint with the correct sourcetype. Mark as `depends_on: [story-core-02]` and have stories `story-app-02`, `story-mw-03`, `story-mw-04`, `story-mcp-02`, `story-mcp-04` list it as a dep.

- **G-C-03 — No story runs a full end-to-end "verdict lands in Splunk" integration test**
  - Expected deliverable: a single integration test that runs `support_agent.py` (or equivalent) against the demo injection payload, verifies the middleware emits a verdict, the OTel exporter ships it to a Splunk instance (live or docker-compose), and an SPL query against the `cisco_ai_defense:splunkgate_verdict` sourcetype returns the event. The demo's plumbing in one test.
  - Why no story covers it: `story-judges-05` ends-to-ends the AI Defense client in isolation; `story-cicd-06` (eval smoke) only hits the AI Defense mock and asserts verdict shape — neither involves Splunk. `story-app-02` notes a sample event round-trip block but only when an env var is set, and only for the props.conf side. `story-app-10` is visual validation (renders against pre-seeded synthetic data, not from a live agent). Nothing wires the full agent-to-dashboard loop.
  - Impact: the most demo-critical promise — that a malicious prompt running through `support_agent.py` produces an event in the Splunk dashboard — is not tested anywhere. The first time anyone runs this end-to-end is during the dress rehearsal, which is risky for a submission deadline.
  - Suggested fix: add `story-eval-06-end-to-end-agent-to-splunk-integration.md` under EPIC-10 (or its own micro-epic) with `depends_on: [story-mw-07, story-core-05-otel-hec-exporter-config, story-app-05]`. Test runs `support_agent.py` with the verbatim demo payload, waits for indexing, runs an SPL query, asserts the verdict appears. Gated on `SPLUNKGATE_SPLUNK_HEC_URL` env var (skip locally, run on nightly + pre-demo CI). Also covers the "demo dress rehearsal" gap implicitly — runs the headline path end-to-end.

- **G-C-04 — No story configures GitHub repo operational concerns (branch protection, secrets, ADR template)**
  - Expected deliverable: stories that, post-`gh repo create`, configure: (a) branch protection on `main` per `cicd-spec.md`'s "Required green checks before merge", (b) GitHub Actions secrets via `gh secret set` for `SPLUNKGATE_AI_DEFENSE_API_KEY`, `SPLUNKGATE_SPLUNK_HEC_TOKEN`, `SPLUNKGATE_SPLUNK_HEC_URL`, `PYPI_API_TOKEN`, `COSIGN_PRIVATE_KEY`, (c) ADR folder convention with a template so new architecture decisions during build don't blow open `docs/architecture.md`.
  - Why no story covers it: searching all 60 stories for "branch protection", "gh secret", "secret set", "github actions secret" returns zero hits. `cicd-spec.md` lists the required checks (`lint`, `typecheck`, `test`, `loc-cap`, `appinspect`, `eval-smoke`, `security`) but no story configures branch protection to enforce them. `docs/adrs/` is mentioned in architecture.md § "Repo structure" but no story creates the folder or a template.
  - Impact: (a) CI checks become advisory — a coding agent can merge red, defeating the gate. (b) Secrets-dependent jobs (eval nightly, signed release, AppInspect-with-API-key, end-to-end Splunk integration test) silently fail or skip on first run, and the human submitter discovers it pre-deadline. (c) Any architecture decision during build either bloats `docs/architecture.md` or lands as undocumented PR description, both bad.
  - Suggested fix: add `story-ops-01-branch-protection-and-secrets.md` under EPIC-01 (or a new EPIC-13 "Repo bring-up post-create") with deliverables: `scripts/configure_repo.sh` (idempotent: runs `gh api ... branches/main/protection -X PUT`, runs `gh secret set` for each required secret, reads values from `~/.splunkgate/secrets.env` or prompts), `docs/runbook/repo-bring-up.md`. Add `story-ops-02-adr-template-and-folder.md` with `docs/adrs/0000-template.md`, `docs/adrs/README.md` (lists the 11 ADRs from architecture.md as `0001-uv-over-poetry.md` … `0011-synthetic-data-folder-spelling.md`).

## Minor coverage gaps

- **G-M-01 — `verify=False` caveat in `splunklib/ai/tools.py:308` not carried into a story**
  - Architecture.md banned-patterns section forbids replicating `verify=False`; story-cicd-07 / story-foundsec-01 / story-judges-02 / story-skel-03 all mention `verify=False` in banned-pattern lists, but no story explicitly tests that the codebase never grows a new `verify=False` usage (CI pattern grep) or that the workaround `SPLUNKGATE_DEV_INSECURE_TLS=1` env-gated escape hatch from architecture.md hard-rule 7 is implemented.
  - Suggested fix: extend `story-cicd-07-security-scan-pipeline.md` to add a grep-fail CI step: `! grep -rE "verify\s*=\s*False" packages/ --include='*.py' --exclude-dir=tests --exclude='ai_defense_mock.py'`.

- **G-M-02 — `AgentLimits` typo (`max_structured_output_retires`) preservation rule not carried into a story**
  - The architecture.md banned-patterns and the verified-grounded-promises section both reference splunklib.ai's typo'd field name. No story enforces that if `splunkgate_mw` interacts with `AgentLimits`, the typo is preserved (otherwise the field silently doesn't bind at runtime).
  - Suggested fix: add a Notes-section bullet to `story-mw-01-package-skeleton-and-public-api.md` and a single CI grep check ("if you wrote `max_structured_output_retries` (corrected spelling) it's a bug — splunklib.ai's field is `max_structured_output_retires`").

- **G-M-03 — No story mirrors the `workspace/context/` knowledge-base into the repo (or documents the dependency loudly)**
  - The spec set assumes coding agents have read access to `../context/` via the file system (architecture.md last paragraph: "the orchestrator-spawned coding agents pulling stories from this spec MUST cite the same context/ files in their PR descriptions"). But the repo lives at `github.com/<abu>/splunkgate`; an agent cloning the bare repo has no `context/`. The PR-template citation rule (story-skel-03) becomes literally impossible to satisfy.
  - Impact: either coding agents work without `context/` (citations break, hallucinations creep in), or the orchestrator clones into a workspace that places `context/` as a sibling (the current setup, but undocumented anywhere in the repo).
  - Suggested fix: extend `story-skel-03-claude-md-and-contribution-conventions.md` Notes section to require CLAUDE.md document this layout explicitly: "this repo assumes `../context/` exists relative to the repo root; clone via the orchestrator OR run `scripts/fetch_context.sh` which mirrors `<context-mirror-bucket>` to `./context/` (gitignored)". Alternative: add a sibling story `story-skel-05-context-mirror-fetch-script.md` that ships `scripts/fetch_context.sh`.

- **G-M-04 — Demo dress rehearsal has no explicit story**
  - The audit prompt asks: "What's the 'demo dress rehearsal' story that runs the full 90-second walkthrough in a clean Splunk Cloud trial and confirms the dashboards render correctly?" `story-demo-01-screencast-and-script` produces the script + asciinema cast + recording README, but does not gate on a clean Splunk Cloud trial — it assumes Abu's verified instance is ready. There's no rehearsal-gated story before EPIC-11 closes.
  - Impact: if any of the dashboards drift between when story-app-10 anchors them and when Abu records, the recording reveals the drift in production. Risk window = end of build to submission.
  - Suggested fix: G-C-03 (end-to-end integration test) substantially covers this — the live-mode variant runs the headline path against a real Splunk instance. Adding a tag `pytest -m demo-rehearsal` and wiring it into `story-demo-01` shell verification as block 12 ("run the dress-rehearsal pytest before recording") closes the gap.

- **G-M-05 — `architecture_diagram.md` / `.pdf` alternative not noted**
  - `research/splunk-agentic-ops-2026/01-prizes-tracks.md` says the filename pattern is verbatim `architecture_diagram.(md|pdf|png)`. `story-readme-02` ships `.png` (light + dark). If `.png` rendering fails on Devpost's preview (e.g., 4K monitor scaling weird), there's no fallback `.md` or `.pdf` for graceful degradation. Minor — `.png` will work — but Devpost's tolerance is unverified.
  - Suggested fix: extend `story-readme-02` to also write `architecture_diagram.md` at the repo root (a 5-line stub markdown that embeds the PNG and lists the same nodes textually for accessibility) — costs 5 LOC, adds resilience.

- **G-M-06 — Per-story PR description format not pinned**
  - `story-skel-03` ships `.github/PULL_REQUEST_TEMPLATE.md` with story-ID + context-citation + green-light checklist. It does NOT pin the orchestrator's per-story PR description format (the format `sahil-pr-audit` expects). If the orchestrator dispatches with a specific PR description schema (story ID, file map summary, BDD result block), the template should match — otherwise `sahil-pr-audit` fails on every PR due to format mismatch.
  - Suggested fix: extend `story-skel-03` to require the PR template include the orchestrator-mandated sections: "Story:", "Files touched:", "BDD result:", "context/ citations:", "Shell verification:" (pass/fail block).

- **G-M-07 — No story covers GitHub Actions secrets configuration documentation**
  - Related to G-C-04 but lighter. Even if secrets are configured manually by Abu via `gh secret set`, there's no `docs/runbook/secrets.md` listing which secrets are needed, what they're for, where to obtain them (Cisco AI Defense Explorer Edition URL, Splunk Cloud HEC token URL, PyPI publish token instructions). A future contributor or post-hackathon adopter has no on-ramp.
  - Suggested fix: roll into G-C-04's `story-ops-01-branch-protection-and-secrets.md`.

## Demo moment trace (Step 1 → 5)

| PRD demo step | Stories that build it | Gap? |
|---|---|---|
| 1 (Open dashboard, see live counters) | story-app-01, story-app-02, story-app-05 (Agent Risk Overview), story-app-09 (icons), story-app-10 (vision validation), **+ MISSING `emit_sample_verdict.py` for "live" counters** | **GAP — G-C-01** |
| 2 (Run demo agent script with malicious prompt) | story-mw-07 (`support_agent.py`, 30 LOC, FSI profile), story-mw-02 (tool middleware), story-mw-03 (model middleware pre-inference scan), story-judges-01..05 (AI Defense client), story-demo-01 (`terminal-script.sh`) | none |
| 3 (Verdict console log + tool call blocked) | story-mw-03 (BLOCK on `ModelInputBlockedBySplunkGate`), story-mw-04 (PII check post-inference), story-mw-02 (tool BLOCK on `ToolBlockedBySplunkGate`), story-foundsec-02 (explanation), story-core-03 (error/trace), story-core-04 (structlog console line format) | none |
| 4 (Counter ticks, drilldown to verdict inspector) | story-core-02 (OTel emitter), story-app-02 (sourcetype parsing), story-app-03 (saved searches + MLTK macros), story-app-05 (Risk Overview drilldown links to inspector), story-app-06 (Verdict Inspector), **+ MISSING OTel→HEC bridge** | **GAP — G-C-02** |
| 5 (PDF export from Regulator Evidence Pack) | story-app-07 (Regulator Evidence Pack dashboard with `export_pdf_action` viz hitting `/services/pdfgen/render`), story-app-04 (KV store for verdict history), story-app-03 (saved searches) | none |

The end-to-end loop (G-C-03) tying steps 2→3→4 together is also missing.

## Judging criteria coverage

| Criterion | Stories that contribute | Verdict |
|---|---|---|
| Technological Implementation (tiebreaker #1) | story-core-01/02/03/04 (typed core + OTel emit), story-judges-01..05 (real AI Defense client + circuit breaker + retries + FastAPI fake e2e test), story-foundsec-01..03 (real \|ai SPL invocation), story-mw-01..07 (all 4 splunklib.ai middleware), story-mcp-01..06 (real MCP server + 4 tools), story-eval-01..05 (eval table), story-cicd-01..08 (full CI/CD), story-app-11..12 (AppInspect + Splunkbase package) | **covered** — strongest pillar; eval table + 4 surfaces + AppInspect-clean + real Splunk integration depth all carried |
| Design | story-app-05/06/07 (3 dashboards), story-app-08 (RBA integration into existing SOC workflow), story-app-09 (icons), story-app-10 (vision validation gate), story-demo-01 (90s screencast with English captions, jump-cuts, no music), story-readme-01 (banner, README shape) | **covered** — DNS Guard-mirroring aesthetic, audit-trail-shape dashboards, validated by Opus 4.7 vision review |
| Potential Impact | story-app-07 (Regulator Evidence Pack — NIST AI RMF / SR 26-2 / EU AI Act / HIPAA / PCI panels), story-app-08 (RBA into existing ES — zero adoption friction for 55K+ Cisco Security Cloud customers), story-mw-07 (FSI/HIPAA/PubSec profiles), story-eval-05 (quantifiable F1/ECE numbers), story-readme-01 (credits incumbents — DNS Guard + MCP Watch + DefenseClaw — frames adoption shape) | **covered** — regulatory framing across 3 jurisdictions + same-sourcetype-as-Cisco-Security-Cloud adoption story is strong |
| Quality of the Idea | story-foundsec-02 (Foundation-Sec as explainer — novel framing per ADR-003), story-dc-01..03 (DefenseClaw integration — depend-don't-rebuild signal), story-mcp-01..06 (parallel-to-Splunk's-MCP rather than registering into it — ADR-004), story-app-07 (multi-jurisdiction regulator evidence pack — commercially empty), story-readme-01 (credits incumbents — shows taste / awareness of prior art) | **covered** — multi-surface peer-callable + interception positioning vs Lasso ($50K/year), Foundation-Sec-as-explainer novelty |

All four criteria have stories building toward them. No gap.

## Audience coverage

| Audience | Story trail | Verdict |
|---|---|---|
| CISO | story-app-05 (Agent Risk Overview — at-a-glance trust signal), story-app-07 (Regulator Evidence Pack — examiner-grade artifact with PDF export, NIST RMF, SR 26-2, EU AI Act), story-app-04 (KV store retention), story-readme-01 (CISO-facing tagline + banner + value-prop sequencing) | **covered** |
| AI platform engineer | story-mw-01..07 (3-line integration `Agent(tool_middleware=[SafetyToolMiddleware(profile=...)])`), story-mcp-06 (Claude Desktop + Cursor config snippets — copy-pasteable MCP configs), story-mw-07 (FSI/HIPAA/PubSec profile presets — no per-customer rule authoring), story-dc-01..03 (DefenseClaw drop-in for non-`splunklib.ai` agents — LangGraph example included) | **covered** |
| SOC analyst | story-app-02 (events land in same `cisco_ai_defense:*` sourcetype family as the Cisco Security Cloud app), story-app-08 (`risk_factors.conf` → ES Risk-Based Alerting → notable events appear in existing ES queue, not a separate SplunkGate queue), story-app-06 (Verdict Inspector drill-down for investigation), story-eval-04 (baselines so FP/FN numbers are defensible to a skeptical analyst) | **covered** |

All three audiences have story trails. No gap.

## Submission-requirement coverage

| Requirement | Story | Verdict |
|---|---|---|
| `architecture_diagram.(md\|pdf\|png)` at repo root | story-readme-02 (ships `architecture_diagram.png` + `architecture_diagram_dark.png` at root, Mermaid source in `docs/assets/architecture.mmd`, deterministic build via `scripts/build_diagrams.sh`, GitHub Actions auto-regen workflow) | **covered** (G-M-05 suggests adding a `.md` companion for graceful degradation, but not blocking) |
| Demo video < 3 min on YouTube | story-demo-01 (90s script + asciinema cast + recording README + 1280×720 thumbnail; final mp4 uploaded by Abu out-of-repo; BDD enforces total ≤ 180s, jump-cuts only, no music) | **covered** |
| Public open-source license auto-detectable by GitHub | story-cicd-01 / story-skel-01 (Apache-2.0 `LICENSE` at repo root); story-app-12 also ships `LICENSE` symlink at app root | **covered** |
| README install + run instructions | story-readme-01 (headline + banner + credits — depends on story-eval-05 for eval numbers); the 10-section README shape from PRD §13 is enforced | **covered** |
| Splunk Hosted Models usage (Foundation-Sec via `\| ai`) | story-foundsec-01 (REST search client), story-foundsec-02 (`\| ai` SPL explanation prompt), story-foundsec-03 (mock + integration test) | **covered** — and used as an explainer per ADR-003, demonstrating intentional model choice |
| Splunk MCP Server usage (our own, parallel to Splunk's) | story-mcp-01..06 (own MCP server with 4 tools + Claude Desktop / Cursor configs alongside Splunk's MCP) — parallel-server pattern per ADR-004 | **covered** |
| Eval table generated | story-eval-04 (three baselines), story-eval-05 (metrics + report generator → `eval/results/latest/summary.md`) | **covered** |
| AppInspect clean | story-cicd-05 (CI gate), story-app-11 (`.appinspect.expect.yaml` + 25 manual checks), story-app-12 (build + verify artifact) | **covered** |
| Multiple commits (not one giant commit) | Implicit — orchestrator dispatches ~60 stories as separate PRs → ~60+ merge commits on main. Not story-owned but architecturally guaranteed. | **covered** |

All Devpost submission requirements have a named story. No gap on the submission front.

## Verdict

The spec set is goal-aligned and audience-aligned. Submission-requirement coverage is complete. The four critical gaps are all in the run-time wiring that makes the demo actually fire (sample event emitter, OTel→HEC bridge, end-to-end integration test, repo bring-up automation). All four are small, narrow stories that fit the existing structure without re-shaping any epic. Adding `story-app-13`, `story-core-05`, `story-eval-06`, and `story-ops-01` + `story-ops-02` (5 new stories total, bringing the count from ~57 to ~62) closes the demo-loop risk and the operational risk before the build phase even starts.

Recommended action: hand the 5-story addition list to the orchestrator before Phase 1 dispatch.

# Epics — Aegis

**Hackathon:** Splunk Agentic Ops Hackathon (Devpost)
**Status:** DRAFT (scope locked 2026-06-05 via ADR-013)
**Total epics:** 12
**Total active stories:** **62** (66 original − 6 DEFERRED via ADR-013 + 3 new: explainer-01, app-14, demo-02. See `sprint-status.yaml` for the 6 deferred IDs.)
**Estimated total build time:** **agent-driven**, no human-hour budget per Abu's no-deadline-pressure rule. Each story scoped to ≤ 400 LOC contribution; orchestrator dispatches in dependency order.

---

## Epic overview (dependency order)

| Epic | Title | Surface | Stories | Depends on |
|---|---|---|---|---|
| **EPIC-02** | **Repo skeleton (uv workspace) + coding standards + 400-LOC enforcement** | Cross-cutting | 4 | None — FIRST (workspace must exist before CI can use it) |
| EPIC-01 | CI/CD foundation | Cross-cutting | 8 | EPIC-02 (CI needs the workspace skeleton to build/test against) |
| EPIC-03 | Core domain types (Verdict, OTel emitter, error model) | Cross-cutting | 5 | EPIC-02 |
| EPIC-04 | Cisco AI Defense Inspection API client (typed, mockable, retries, circuit breaker) | Judgment layer | 6 | EPIC-03 |
| EPIC-05 | Verdict explainer (template v1, Foundation-Sec future per ADR-013) | Judgment layer | 1 active + 3 DEFERRED | EPIC-03 |
| EPIC-06 | **Surface 1** — aegis-mw middleware library for splunklib.ai | S1 | 7 | EPIC-03, EPIC-04, EPIC-05 |
| EPIC-07 | **Surface 2** — Aegis MCP Server (own, parallel to Splunk's app 7931) | S2 | 4 active + 2 DEFERRED | EPIC-03, EPIC-04, EPIC-05 |
| EPIC-08 | **Surface 3** — DefenseClaw integration (config docs only, ADR-013) | S3 | 1 active + 2 DEFERRED | EPIC-03 |
| EPIC-09 | **Surface 4** — Splunk app (SPL/MLTK + 3 Dashboard Studio v2 dashboards + MITRE ATLAS lookup) | S4 | 12 | EPIC-03 (events) |
| EPIC-10 | Eval harness + synthetic data generator | Cross-cutting | 6 | EPIC-04, EPIC-05, EPIC-06 |
| EPIC-11 | Demo video assets + README + architecture diagrams + SAIA NL→SPL scene | Cross-cutting | 4 | All build epics |
| EPIC-12 | AppInspect compliance hardening + Splunkbase prep + GitHub ops | Cross-cutting | 4 | EPIC-09, EPIC-01 |

---

## EPIC-01 — CI/CD foundation

**Business value:** Every subsequent epic (after the workspace exists) depends on the pipeline being green. If CI/CD isn't right, every coding agent wastes work fighting it.

**Anchor doc:** `docs/cicd-spec.md`

**Dependencies:** EPIC-02 (CI must build/test against the uv workspace skeleton — workspace ownership lives in story-skel-01, owned by EPIC-02; per audit synthesis Block C the EPIC-02 → EPIC-01 order is the canonical dispatch direction)
**Stories:** 8
**Files under `docs/stories/`:**
- `story-cicd-01-build-pipeline-python-wheels.md`
- `story-cicd-02-test-pipeline-pytest-respx.md`
- `story-cicd-03-loc-cap-enforcement.md`
- `story-cicd-04-pre-commit-hooks.md`
- `story-cicd-05-appinspect-gate.md`
- `story-cicd-06-eval-smoke-job.md`
- `story-cicd-07-security-scan-pipeline.md`
- `story-cicd-08-release-pipeline-signed.md`

---

## EPIC-02 — Repo skeleton + coding standards + 400-LOC enforcement

**Business value:** Locks the monorepo layout (uv workspace), dep manifests, formatter / linter / typechecker configs, contribution conventions. Per audit synthesis Block C, story-skel-01 (uv workspace + 4 package shells + eval pyproject) is the FIRST story in the whole project — CI cannot build a workspace that doesn't exist.

**Anchor doc:** `docs/architecture.md` § "Repo structure", § "Coding standards"

**Dependencies:** None — FIRST (story-skel-01 ships the uv workspace skeleton; EPIC-01 then builds CI on top). Story-skel-02 (ruff/mypy), story-skel-03 (CLAUDE.md), and story-skel-04 (pre-commit verification) can land after the EPIC-01 stories.
**Stories:** 4
**Files under `docs/stories/`:**
- `story-skel-01-uv-workspace-pyproject.md`
- `story-skel-02-ruff-mypy-config.md`
- `story-skel-03-claude-md-and-contribution-conventions.md`
- `story-skel-04-loc-check-script-and-pre-commit.md`

---

## EPIC-03 — Core domain types

**Business value:** Every surface uses `Verdict`, `Severity`, OTel emission helpers. Without this, surfaces fork into incompatible types and integration becomes refactor-or-die.

**Anchor doc:** `docs/architecture.md` § "API schemas"

**Dependencies:** EPIC-02
**Stories:** 5
**Files under `docs/stories/`:**
- `story-core-01-verdict-pydantic-types.md`
- `story-core-02-otel-evaluation-event-emitter.md`
- `story-core-03-error-model-and-trace-propagation.md`
- `story-core-04-structlog-config-and-conventions.md`
- `story-core-05-otel-hec-exporter-config.md`

---

## EPIC-04 — Cisco AI Defense Inspection API client

**Business value:** This is the binary classifier in the judgment layer. Aegis stands on this. Mockable for dev, typed for safety, resilient under failure.

**Anchor doc:** `context/07-cisco-stack/01-ai-defense-deep.md`

**Dependencies:** EPIC-03
**Stories:** 6
**Files under `docs/stories/`:**
- `story-judges-01-ai-defense-request-response-models.md`
- `story-judges-02-ai-defense-httpx-client-with-retries.md`
- `story-judges-03-ai-defense-circuit-breaker-tenacity.md`
- `story-judges-04-ai-defense-mock-respx-fixtures.md`
- `story-judges-05-ai-defense-end-to-end-integration-test.md`
- `story-judges-06-defenseclaw-python-shim.md`

---

## EPIC-05 — Verdict explainer (template v1, Foundation-Sec future)

**Business value:** The explanation layer — the WHY-string the dashboard, regulator-evidence-pack PDF, and demo video all surface. v1 ships a deterministic template-based explainer that populates `Verdict.explanation` from already-decided verdict fields. Per ADR-013, the Foundation-Sec implementation is deferred until Splunk Slack confirms Trial-tier Hosted Models access; the swap is a one-file change inside `aegis_judges/explainer.py`. ADR-003's "explainer-only, never classifier" invariant holds across both implementations.

**Anchor doc:** `context/07-cisco-stack/03-foundation-sec-models.md`, `context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md`, ADR-003 + ADR-013 in `docs/architecture.md`

**Dependencies:** EPIC-03
**Active stories:** 1
**Files under `docs/stories/`:**
- `story-explainer-01-template-based-verdict-explainer.md` (NEW — v1 implementation)
- `story-foundsec-01-splunk-rest-search-client.md` (⚠ DEFERRED per ADR-003a)
- `story-foundsec-02-ai-spl-explanation-prompt.md` (⚠ DEFERRED per ADR-013)
- `story-foundsec-03-foundation-sec-mock-and-integration-test.md` (⚠ DEFERRED per ADR-013)

---

## EPIC-06 — Surface 1: aegis-mw middleware library

**Business value:** The lowest-friction surface for `splunklib.ai`-built agents. Pre-emit interception in 3 lines of agent code. The Splunk-native pitch.

**Anchor doc:** `docs/architecture.md` § "Surface 1", `context/02-agent-frameworks/06-splunklib-ai-deep-read.md`

**Dependencies:** EPIC-03, EPIC-04, EPIC-05
**Stories:** 7
**Files under `docs/stories/`:**
- `story-mw-01-package-skeleton-and-public-api.md`
- `story-mw-02-tool-middleware-with-defenseclaw-args.md`
- `story-mw-03-model-middleware-pre-inference-scan.md`
- `story-mw-04-model-middleware-post-inference-pii-check.md`
- `story-mw-05-subagent-middleware.md`
- `story-mw-06-agent-middleware-trace-correlation.md`
- `story-mw-07-profiles-and-config-fsi-hipaa-pubsec.md`

---

## EPIC-07 — Surface 2: Aegis MCP Server

**Business value:** The Splunk-agnostic / framework-agnostic surface. Any MCP client can call us. The MCP bonus prize.

**Anchor doc:** `docs/architecture.md` § "Surface 2", `context/10-standards/01-mcp-spec-deep.md`

**Dependencies:** EPIC-03, EPIC-04, EPIC-05
**Active stories:** 4 (slimmed from 6 per ADR-013 — skeleton + 1 hero tool + 1 supporting tool + Claude Desktop coexistence config)
**Files under `docs/stories/`:**
- `story-mcp-01-server-skeleton-with-mcp-python-sdk.md`
- `story-mcp-02-tool-score-prompt-injection.md`
- `story-mcp-03-tool-judge-tool-call.md`
- `story-mcp-04-tool-check-output-leak.md` (⚠ DEFERRED per ADR-013)
- `story-mcp-05-tool-audit-trace.md` (⚠ DEFERRED per ADR-013)
- `story-mcp-06-claude-desktop-cursor-config-examples.md` (NOW references Splunk MCP Server app 7931 for concrete coexistence demo)

---

## EPIC-08 — Surface 3: DefenseClaw integration

**Business value:** The "any-agent-any-framework" surface. Catches HTTP traffic from agents that don't import our middleware. We depend on DefenseClaw, contribute back upstream.

**Anchor doc:** `docs/architecture.md` § "Surface 3", `context/sources/code-snippets/defenseclaw-splunk_hec-top100.go`

**Dependencies:** EPIC-03
**Active stories:** 1 (config docs only; ADR-013 deferred the upstream PR + LangGraph example)
**Files under `docs/stories/`:**
- `story-dc-01-config-delta-docs-and-example.md`
- `story-dc-02-ai-defense-backend-upstream-pr.md` (⚠ DEFERRED per ADR-013)
- `story-dc-03-langgraph-example-agent.md` (⚠ DEFERRED per ADR-013)

---

## EPIC-09 — Surface 4: Splunk app

**Business value:** The Splunk-native winning shape (DNS Guard 2025 pattern). The CISO + SOC analyst + examiner UI. Where the audit trail lives.

**Anchor doc:** `docs/architecture.md` § "Repo structure" > `splunk_apps/aegis_app/`, `docs/ux-spec.md`, `docs/eval-spec.md`

**Dependencies:** EPIC-03 (event shape must be locked before SPL parsing rules are written)
**Active stories:** 12 (added `story-app-14` per ADR-013 — MITRE ATLAS technique-ID lookup)
**Files under `docs/stories/`:**
- `story-app-01-app-conf-and-metadata-skeleton.md`
- `story-app-02-props-transforms-for-aegis-verdict-sourcetype.md`
- `story-app-03-savedsearches-and-mltk-macros.md`
- `story-app-04-collections-conf-kvstore-verdict-history.md`
- `story-app-05-dashboard-agent-risk-overview.md`
- `story-app-06-dashboard-verdict-inspector.md`
- `story-app-07-dashboard-regulator-evidence-pack.md`
- `story-app-08-risk-factors-conf-es-rba-integration.md`
- `story-app-09-static-icons-and-app-assets.md`
- `story-app-10-app-vision-loop-validation.md`
- `story-app-13-synthetic-verdict-emitter-script.md`
- `story-app-14-mitre-atlas-technique-mapping.md` (NEW per ADR-013 — open-standards interoperability)

---

## EPIC-10 — Eval harness + synthetic data generator

**Business value:** The eval table is the headline of the submission. Without it, all four surfaces are vibes. With it, judges have numbers.

**Anchor doc:** `docs/eval-spec.md`

**Dependencies:** EPIC-04 (need AI Defense client), EPIC-05 (need Foundation-Sec for explanation comparison), EPIC-06 (S1 is end-to-end the easiest to run eval through)
**Stories:** 6
**Files under `docs/stories/`:**
- `story-eval-01-synthetic-data-generator-dns-guard-pattern.md`
- `story-eval-02-jailbreakbench-and-advbench-loaders.md`
- `story-eval-03-imprompter-payload-corpus-from-pdf.md`
- `story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone.md`
- `story-eval-05-metrics-and-report-generator.md`
- `story-eval-06-end-to-end-agent-to-splunk-integration.md`

---

## EPIC-11 — Demo video assets + README + architecture diagrams

**Business value:** Judges read README before they demo. Demo video < 3 min is a non-negotiable submission requirement. Architecture diagram is non-negotiable submission requirement. Direct scoring lever.

**Anchor doc:** `docs/PRD.md` § "Demo moment", `research/splunk-agentic-ops-2026/01-prizes-tracks.md`

**Dependencies:** EPIC-01 through EPIC-10 complete (so README has real eval numbers)
**Active stories:** 4 (added `story-demo-02` per ADR-013 — SAIA NL→SPL demo scene)
**Files under `docs/stories/`:**
- `story-readme-01-headline-and-banner-and-credits.md`
- `story-readme-02-architecture-diagrams-light-dark-png.md`
- `story-demo-01-screencast-and-script.md`
- `story-demo-02-saia-nl-query-demo-moment.md` (NEW per ADR-013 — Scene 4 SAIA NL→SPL → live dashboard update)

---

## EPIC-12 — AppInspect compliance hardening + Splunkbase prep + GitHub Ops

**Business value:** Mirroring CIMplicity AI 2025 winner's pattern (`.appinspect.expect.yaml` + `.appinspect.manualcheck.yaml`) signals to Splunk staff judges that we know what shipping a Splunkbase app actually requires. Optional Splunkbase submission for post-hackathon distribution. Also lands the GitHub-side operational config (branch protection + secrets registry + ADR template) that `docs/cicd-spec.md` § "Acceptance for the CI/CD epic as a whole" requires.

**Anchor doc:** `context/05-splunk-core/09-appinspect.md`, `context/11-prior-art/01-build-a-thon-2025-deep-read.md`, `docs/cicd-spec.md` § "Branch protection" + § "Secrets to configure in GitHub"

**Dependencies:** EPIC-09 (AppInspect stories), EPIC-01 (Ops stories — CI workflows must exist before branch protection can reference them)
**Stories:** 4
**Files under `docs/stories/`:**
- `story-app-11-appinspect-expect-yaml-and-manual-checks.md`
- `story-app-12-splunkbase-submission-package-and-checklist.md`
- `story-ops-01-branch-protection-config.md`
- `story-ops-02-github-secrets-and-adr-template.md`

---

## Implementation order (for orchestrator dispatch queue)

The orchestrator dispatches stories in this exact order, respecting cross-epic dependencies. Stories WITHIN an epic can run in parallel (orchestrator decides based on internal `depends_on` in each story file).

```yaml
dispatch_queue:
  # ---- EPIC-02 (repo skeleton — must land FIRST so CI has a workspace to build) ----
  - story-skel-01-uv-workspace-pyproject

  # ---- EPIC-01 (CI/CD foundation — depends on skel-01) ----
  - story-cicd-01-build-pipeline-python-wheels
  - story-cicd-02-test-pipeline-pytest-respx
  - story-cicd-03-loc-cap-enforcement
  - story-cicd-04-pre-commit-hooks
  - story-cicd-05-appinspect-gate
  - story-cicd-06-eval-smoke-job
  - story-cicd-07-security-scan-pipeline
  - story-cicd-08-release-pipeline-signed

  # ---- EPIC-02 remainder (after CI is green) ----
  - story-skel-02-ruff-mypy-config
  - story-skel-03-claude-md-and-contribution-conventions
  - story-skel-04-loc-check-script-and-pre-commit

  # ---- EPIC-03 (core types) ----
  - story-core-01-verdict-pydantic-types
  - story-core-02-otel-evaluation-event-emitter
  - story-core-03-error-model-and-trace-propagation
  - story-core-04-structlog-config-and-conventions
  - story-core-05-otel-hec-exporter-config

  # ---- EPIC-04 + EPIC-05 (judgment layer) — can run in parallel ----
  - story-judges-01-ai-defense-request-response-models
  - story-judges-02-ai-defense-httpx-client-with-retries
  - story-judges-03-ai-defense-circuit-breaker-tenacity
  - story-judges-04-ai-defense-mock-respx-fixtures
  - story-judges-05-ai-defense-end-to-end-integration-test
  # foundsec-01/-02/-03 DEFERRED per ADR-013 — superseded by story-explainer-01 below.
  - story-explainer-01-template-based-verdict-explainer  # NEW — v1 explainer per ADR-013

  # ---- EPIC-06 + EPIC-07 + EPIC-08 (surfaces 1, 2, 3) — can run in parallel ----
  - story-mw-01-package-skeleton-and-public-api
  - story-mw-02-tool-middleware-with-defenseclaw-args
  - story-mw-03-model-middleware-pre-inference-scan
  - story-mw-04-model-middleware-post-inference-pii-check
  - story-mw-05-subagent-middleware
  - story-mw-06-agent-middleware-trace-correlation
  - story-mw-07-profiles-and-config-fsi-hipaa-pubsec
  - story-mcp-01-server-skeleton-with-mcp-python-sdk
  - story-mcp-02-tool-score-prompt-injection
  - story-mcp-03-tool-judge-tool-call
  # mcp-04 + mcp-05 DEFERRED per ADR-013 — redundant with S1 + S4 surfaces.
  - story-mcp-06-claude-desktop-cursor-config-examples
  - story-dc-01-config-delta-docs-and-example
  # dc-02 + dc-03 DEFERRED per ADR-013 — out-of-our-control merge + not load-bearing for Security track.
  - story-judges-06-defenseclaw-python-shim   # EPIC-04 — depends on dc-01 (rule pack provenance) + core-01

  # ---- EPIC-09 (Surface 4 — Splunk app) — sequential within epic ----
  - story-app-01-app-conf-and-metadata-skeleton
  - story-app-02-props-transforms-for-aegis-verdict-sourcetype
  - story-app-13-synthetic-verdict-emitter-script   # after app-02 (sourcetype config) + eval-01 (corpora); unblocks app-10 + demo-01
  - story-app-03-savedsearches-and-mltk-macros
  - story-app-04-collections-conf-kvstore-verdict-history
  - story-app-05-dashboard-agent-risk-overview
  - story-app-06-dashboard-verdict-inspector
  - story-app-07-dashboard-regulator-evidence-pack
  - story-app-08-risk-factors-conf-es-rba-integration
  - story-app-09-static-icons-and-app-assets
  - story-app-10-app-vision-loop-validation
  - story-app-14-mitre-atlas-technique-mapping  # NEW per ADR-013 — open-standards lookup

  # ---- EPIC-10 (eval) ----
  - story-eval-01-synthetic-data-generator-dns-guard-pattern
  - story-eval-02-jailbreakbench-and-advbench-loaders
  - story-eval-03-imprompter-payload-corpus-from-pdf
  - story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone
  - story-eval-05-metrics-and-report-generator
  - story-eval-06-end-to-end-agent-to-splunk-integration   # after mw-07 + app-13 + core-05; dress rehearsal for demo

  # ---- EPIC-12 (AppInspect hardening + GitHub Ops — must run before EPIC-11) ----
  - story-app-11-appinspect-expect-yaml-and-manual-checks
  - story-app-12-splunkbase-submission-package-and-checklist
  - story-ops-01-branch-protection-config            # after cicd-07; documents + scripts main-branch protection
  - story-ops-02-github-secrets-and-adr-template     # after cicd-07 + skel-03; secrets registry + docs/adrs/ bootstrap

  # ---- EPIC-11 (README + demo video — LAST) ----
  - story-readme-01-headline-and-banner-and-credits
  - story-readme-02-architecture-diagrams-light-dark-png
  - story-demo-01-screencast-and-script
  - story-demo-02-saia-nl-query-demo-moment  # NEW per ADR-013 — Scene 4 SAIA NL→SPL
```

Total: **62 active stories** (66 original − 6 DEFERRED + 3 NEW per ADR-013).

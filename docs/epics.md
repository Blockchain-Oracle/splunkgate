# Epics — Aegis

**Hackathon:** Splunk Agentic Ops Hackathon (Devpost)
**Status:** DRAFT (locks after Abu approval)
**Total epics:** 12
**Total stories:** ~57 (final count after stories land — see `sprint-status.yaml`)
**Estimated total build time:** **agent-driven**, no human-hour budget per Abu's no-deadline-pressure rule. Each story scoped to ≤ 400 LOC contribution; orchestrator dispatches in dependency order.

---

## Epic overview (dependency order)

| Epic | Title | Surface | Stories | Depends on |
|---|---|---|---|---|
| **EPIC-01** | **CI/CD foundation** | Cross-cutting | 8 | None — FIRST |
| EPIC-02 | Repo skeleton + coding standards + 400-LOC enforcement | Cross-cutting | 4 | EPIC-01 |
| EPIC-03 | Core domain types (Verdict, OTel emitter, error model) | Cross-cutting | 4 | EPIC-02 |
| EPIC-04 | Cisco AI Defense Inspection API client (typed, mockable, retries, circuit breaker) | Judgment layer | 5 | EPIC-03 |
| EPIC-05 | Foundation-Sec invocation via \| ai SPL (explainer, NOT judge) | Judgment layer | 3 | EPIC-03 |
| EPIC-06 | **Surface 1** — aegis-mw middleware library for splunklib.ai | S1 | 7 | EPIC-03, EPIC-04, EPIC-05 |
| EPIC-07 | **Surface 2** — Aegis MCP Server (own, parallel to Splunk's) | S2 | 6 | EPIC-03, EPIC-04, EPIC-05 |
| EPIC-08 | **Surface 3** — DefenseClaw integration | S3 | 3 | EPIC-03 |
| EPIC-09 | **Surface 4** — Splunk app (SPL/MLTK + 3 Dashboard Studio v2 dashboards) | S4 | 10 | EPIC-03 (events) |
| EPIC-10 | Eval harness + synthetic data generator | Cross-cutting | 5 | EPIC-04, EPIC-05, EPIC-06 |
| EPIC-11 | Demo video assets + README + architecture diagrams | Cross-cutting | 3 | All build epics |
| EPIC-12 | AppInspect compliance hardening + optional Splunkbase submission prep | Cross-cutting | 2 | EPIC-09 |

---

## EPIC-01 — CI/CD foundation

**Business value:** Every subsequent epic depends on the pipeline being green. If CI/CD isn't right, every coding agent wastes work fighting it. This is the foundation. Abu's explicit instruction.

**Anchor doc:** `docs/cicd-spec.md`

**Dependencies:** None
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

**Business value:** Locks the monorepo layout, dep manifests, formatter / linter / typechecker configs, contribution conventions. Without these, every coding agent picks a different style and PRs become unreviewable.

**Anchor doc:** `docs/architecture.md` § "Repo structure", § "Coding standards"

**Dependencies:** EPIC-01 (CI must enforce these)
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
**Stories:** 4
**Files under `docs/stories/`:**
- `story-core-01-verdict-pydantic-types.md`
- `story-core-02-otel-evaluation-event-emitter.md`
- `story-core-03-error-model-and-trace-propagation.md`
- `story-core-04-structlog-config-and-conventions.md`

---

## EPIC-04 — Cisco AI Defense Inspection API client

**Business value:** This is the binary classifier in the judgment layer. Aegis stands on this. Mockable for dev, typed for safety, resilient under failure.

**Anchor doc:** `context/07-cisco-stack/01-ai-defense-deep.md`

**Dependencies:** EPIC-03
**Stories:** 5
**Files under `docs/stories/`:**
- `story-judges-01-ai-defense-request-response-models.md`
- `story-judges-02-ai-defense-httpx-client-with-retries.md`
- `story-judges-03-ai-defense-circuit-breaker-tenacity.md`
- `story-judges-04-ai-defense-mock-respx-fixtures.md`
- `story-judges-05-ai-defense-end-to-end-integration-test.md`

---

## EPIC-05 — Foundation-Sec invocation via `| ai` SPL

**Business value:** The explanation layer — the WHY-string the dashboard shows alongside the verdict. Cisco markets Foundation-Sec as security copilot (verified). Used as built.

**Anchor doc:** `context/07-cisco-stack/03-foundation-sec-models.md`, `context/06-splunk-ai-stack/07-foundation-sec-on-splunk.md`

**Dependencies:** EPIC-03
**Stories:** 3
**Files under `docs/stories/`:**
- `story-foundsec-01-splunk-rest-search-client.md`
- `story-foundsec-02-ai-spl-explanation-prompt.md`
- `story-foundsec-03-foundation-sec-mock-and-integration-test.md`

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
**Stories:** 6
**Files under `docs/stories/`:**
- `story-mcp-01-server-skeleton-with-mcp-python-sdk.md`
- `story-mcp-02-tool-score-prompt-injection.md`
- `story-mcp-03-tool-judge-tool-call.md`
- `story-mcp-04-tool-check-output-leak.md`
- `story-mcp-05-tool-audit-trace.md`
- `story-mcp-06-claude-desktop-cursor-config-examples.md`

---

## EPIC-08 — Surface 3: DefenseClaw integration

**Business value:** The "any-agent-any-framework" surface. Catches HTTP traffic from agents that don't import our middleware. We depend on DefenseClaw, contribute back upstream.

**Anchor doc:** `docs/architecture.md` § "Surface 3", `context/sources/code-snippets/defenseclaw-splunk_hec-top100.go`

**Dependencies:** EPIC-03
**Stories:** 3
**Files under `docs/stories/`:**
- `story-dc-01-config-delta-docs-and-example.md`
- `story-dc-02-ai-defense-backend-upstream-pr.md`
- `story-dc-03-langgraph-example-agent.md`

---

## EPIC-09 — Surface 4: Splunk app

**Business value:** The Splunk-native winning shape (DNS Guard 2025 pattern). The CISO + SOC analyst + examiner UI. Where the audit trail lives.

**Anchor doc:** `docs/architecture.md` § "Repo structure" > `splunk_apps/aegis_app/`, `docs/ux-spec.md`, `docs/eval-spec.md`

**Dependencies:** EPIC-03 (event shape must be locked before SPL parsing rules are written)
**Stories:** 10
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

---

## EPIC-10 — Eval harness + synthetic data generator

**Business value:** The eval table is the headline of the submission. Without it, all four surfaces are vibes. With it, judges have numbers.

**Anchor doc:** `docs/eval-spec.md`

**Dependencies:** EPIC-04 (need AI Defense client), EPIC-05 (need Foundation-Sec for explanation comparison), EPIC-06 (S1 is end-to-end the easiest to run eval through)
**Stories:** 5
**Files under `docs/stories/`:**
- `story-eval-01-synthetic-data-generator-dns-guard-pattern.md`
- `story-eval-02-jailbreakbench-and-advbench-loaders.md`
- `story-eval-03-imprompter-payload-corpus-from-pdf.md`
- `story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone.md`
- `story-eval-05-metrics-and-report-generator.md`

---

## EPIC-11 — Demo video assets + README + architecture diagrams

**Business value:** Judges read README before they demo. Demo video < 3 min is a non-negotiable submission requirement. Architecture diagram is non-negotiable submission requirement. Direct scoring lever.

**Anchor doc:** `docs/PRD.md` § "Demo moment", `context/01-prizes-tracks.md`

**Dependencies:** EPIC-01 through EPIC-10 complete (so README has real eval numbers)
**Stories:** 3
**Files under `docs/stories/`:**
- `story-readme-01-headline-and-banner-and-credits.md`
- `story-readme-02-architecture-diagrams-light-dark-png.md`
- `story-demo-01-screencast-and-script.md`

---

## EPIC-12 — AppInspect compliance hardening + Splunkbase submission prep

**Business value:** Mirroring CIMplicity AI 2025 winner's pattern (`.appinspect.expect.yaml` + `.appinspect.manualcheck.yaml`) signals to Splunk staff judges that we know what shipping a Splunkbase app actually requires. Optional Splunkbase submission for post-hackathon distribution.

**Anchor doc:** `context/05-splunk-core/09-appinspect.md`, `context/11-prior-art/01-build-a-thon-2025-deep-read.md`

**Dependencies:** EPIC-09
**Stories:** 2
**Files under `docs/stories/`:**
- `story-app-11-appinspect-expect-yaml-and-manual-checks.md`
- `story-app-12-splunkbase-submission-package-and-checklist.md`

---

## Implementation order (for orchestrator dispatch queue)

The orchestrator dispatches stories in this exact order, respecting cross-epic dependencies. Stories WITHIN an epic can run in parallel (orchestrator decides based on internal `depends_on` in each story file).

```yaml
dispatch_queue:
  # ---- EPIC-01 (foundation) ----
  - story-cicd-01-build-pipeline-python-wheels
  - story-cicd-02-test-pipeline-pytest-respx
  - story-cicd-03-loc-cap-enforcement
  - story-cicd-04-pre-commit-hooks
  - story-cicd-05-appinspect-gate
  - story-cicd-06-eval-smoke-job
  - story-cicd-07-security-scan-pipeline
  - story-cicd-08-release-pipeline-signed

  # ---- EPIC-02 (repo skeleton) ----
  - story-skel-01-uv-workspace-pyproject
  - story-skel-02-ruff-mypy-config
  - story-skel-03-claude-md-and-contribution-conventions
  - story-skel-04-loc-check-script-and-pre-commit

  # ---- EPIC-03 (core types) ----
  - story-core-01-verdict-pydantic-types
  - story-core-02-otel-evaluation-event-emitter
  - story-core-03-error-model-and-trace-propagation
  - story-core-04-structlog-config-and-conventions

  # ---- EPIC-04 + EPIC-05 (judgment layer) — can run in parallel ----
  - story-judges-01-ai-defense-request-response-models
  - story-judges-02-ai-defense-httpx-client-with-retries
  - story-judges-03-ai-defense-circuit-breaker-tenacity
  - story-judges-04-ai-defense-mock-respx-fixtures
  - story-judges-05-ai-defense-end-to-end-integration-test
  - story-foundsec-01-splunk-rest-search-client
  - story-foundsec-02-ai-spl-explanation-prompt
  - story-foundsec-03-foundation-sec-mock-and-integration-test

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
  - story-mcp-04-tool-check-output-leak
  - story-mcp-05-tool-audit-trace
  - story-mcp-06-claude-desktop-cursor-config-examples
  - story-dc-01-config-delta-docs-and-example
  - story-dc-02-ai-defense-backend-upstream-pr
  - story-dc-03-langgraph-example-agent

  # ---- EPIC-09 (Surface 4 — Splunk app) — sequential within epic ----
  - story-app-01-app-conf-and-metadata-skeleton
  - story-app-02-props-transforms-for-aegis-verdict-sourcetype
  - story-app-03-savedsearches-and-mltk-macros
  - story-app-04-collections-conf-kvstore-verdict-history
  - story-app-05-dashboard-agent-risk-overview
  - story-app-06-dashboard-verdict-inspector
  - story-app-07-dashboard-regulator-evidence-pack
  - story-app-08-risk-factors-conf-es-rba-integration
  - story-app-09-static-icons-and-app-assets
  - story-app-10-app-vision-loop-validation

  # ---- EPIC-10 (eval) ----
  - story-eval-01-synthetic-data-generator-dns-guard-pattern
  - story-eval-02-jailbreakbench-and-advbench-loaders
  - story-eval-03-imprompter-payload-corpus-from-pdf
  - story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone
  - story-eval-05-metrics-and-report-generator

  # ---- EPIC-12 (AppInspect hardening — must run before EPIC-11) ----
  - story-app-11-appinspect-expect-yaml-and-manual-checks
  - story-app-12-splunkbase-submission-package-and-checklist

  # ---- EPIC-11 (README + demo video — LAST) ----
  - story-readme-01-headline-and-banner-and-credits
  - story-readme-02-architecture-diagrams-light-dark-png
  - story-demo-01-screencast-and-script
```

Total: ~57 stories.

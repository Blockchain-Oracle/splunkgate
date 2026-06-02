# 2026-06-02 — Aegis Spec Set Design (Brainstorm Output)

> Output of the brainstorming-skill Phase 1–3 pass. Approved by Abu on 2026-06-02. Input to `sahil-spec-writer`.

## Decisions captured

| Decision | Value | Rationale |
|---|---|---|
| **Project name** | **Aegis** | Mythological shield (Athena/Zeus). Clean PyPI + Splunk app ID availability. Maps cleanly to "shield in front of the agent." Approved by Abu over `Argus` and `Bastion` candidates. |
| **License** | **Apache-2.0** | Permissive + patent grant. Plays with DefenseClaw (also Apache-2.0). Auto-detectable per Hackathon submission rule. |
| **Repo location** | `workspace/aegis/` (local) | Local skeleton now; `gh repo create` after specs approved. |
| **Build sequence** | **End-to-end one-pass** — every spec ships in one pass. CI/CD is Epic 01 (FIRST in execution order) but the spec set does not "leave anything behind for later." | Abu's explicit instruction: "We should write everything end-to-end. Why are we leaving some specs behind and coming back to write it again?" |
| **Architecture source of truth** | `../research/splunk-agentic-ops-2026/13-architecture-recommendation-v2.md` | Verified-grounded. Supersedes `11-` (which has a warning header pointing here). |
| **Domain knowledge source of truth** | `../context/` (12 folders + audit + sources/) | All claims flagged ✅/🟡/❓/❌. Spec writer references back to specific context files for every load-bearing fact. |
| **Coding constraints** | Every source file ≤400 LOC; enforced via pre-commit + CI fail-on-exceed | Abu's explicit instruction. |
| **Spec convention** | `sahil-spec-writer` (BMad-style) — `docs/PRD.md`, `docs/architecture.md`, `docs/ux-spec.md`, `docs/epics.md`, `docs/stories/*.md` — plus two custom: `docs/cicd-spec.md` and `docs/eval-spec.md` | Sahil's convention + Abu's explicit ask for CI/CD as a dedicated spec. |
| **Story shape** | BDD `Given/When/Then` acceptance criteria. Each story scoped to ≤400 LOC contribution. Each story cross-references `context/` for any domain fact it depends on. | Hand-off to coding agents must be no-research-required. |
| **No vertical slice MVP** | All four surfaces in v1 | Abu's "no deadline pressure, full appetite, end-to-end" rule. |

## Spec inventory (7 files + ~50–60 stories)

| # | File | Purpose | Length target |
|---|---|---|---|
| 1 | `docs/PRD.md` | Product vision, audience, success criteria, scope, out-of-scope, regulatory framing | 4–6 pages |
| 2 | `docs/architecture.md` | Formalized 13-recommendation-v2: 4 surfaces, monorepo file/folder structure, library choices with verified justification, API schemas (Verdict / OTel GenAI / MCP `outputSchema` / AI Defense client), coding standards (400 LOC enforcement, typing strictness, testing, security hygiene) | 12–18 pages |
| 3 | `docs/cicd-spec.md` | **First execution epic.** Build pipeline (sentinel-mw wheel + Aegis MCP server + Splunk app `.tgz`) · Test pipeline (unit + integration + contract + eval) · AppInspect gate on every PR · Security scans (pip-audit, gitleaks, trivy) · Release pipeline (signed artifacts, version tags, changelog generation) · 400-LOC enforcement (pre-commit + CI fail-on-exceed) | 6–8 pages |
| 4 | `docs/eval-spec.md` | Datasets (JailbreakBench, AdvBench, custom synthetic per Imprompter findings); Metrics (precision, recall, F1, ECE, p50/p99 latency, cost-per-1k); Baselines (DefenseClaw regex-only · gpt-oss-120b-as-judge · AI Defense alone) | 4 pages |
| 5 | `docs/ux-spec.md` | Three Dashboard Studio v2 dashboards for Surface 4 — Agent Risk Overview, Verdict Inspector, Regulator Evidence Pack (PDF export). Wireframes + Dashboard Studio JSON skeletons | 4–6 pages |
| 6 | `docs/epics.md` | Ordered epic list (12 epics, CI/CD first, foundation-first within scope) | 2 pages |
| 7 | `docs/stories/story-*.md` | ~50–60 individual GitHub-issue-ready stories. BDD acceptance criteria. Cross-referenced to `context/` for every load-bearing fact. Each story scoped to ≤400 LOC contribution. | ~50–60 files |

## Epic list (the spine of `docs/epics.md`)

Numbering = execution priority. Spec writes ALL epics' stories in one pass; agents execute serially in numbered order.

| Epic | Title | Surface | Approx stories |
|---|---|---|---|
| **EPIC-01** | **CI/CD foundation** (build / test / AppInspect / security / release) | Cross-cutting | 6–8 |
| EPIC-02 | Repo skeleton + coding standards + 400-LOC enforcement | Cross-cutting | 3–4 |
| EPIC-03 | Core domain types — `Verdict`, `Severity`, OTel emission helpers, error model | Cross-cutting | 3–4 |
| EPIC-04 | Cisco AI Defense Inspection API client (typed, mockable, retries, circuit breaker) | Judgment layer | 4–5 |
| EPIC-05 | Foundation-Sec invocation client via `\| ai` SPL (explainer, not judge) | Judgment layer | 3 |
| EPIC-06 | **Surface 1** — `aegis-mw` middleware library for `splunklib.ai` (uses real 4-middleware API) | S1 | 6–8 |
| EPIC-07 | **Surface 2** — Aegis MCP Server (own, parallel to Splunk's official server) | S2 | 5–7 |
| EPIC-08 | **Surface 3** — DefenseClaw integration (config delta + upstream PR adding AI Defense backend) | S3 | 3–4 |
| EPIC-09 | **Surface 4** — Splunk app (SPL searches, MLTK macros mirroring DNS Guard's `fit DensityFunction` + `fit KMeans` pattern, 3 Dashboard Studio v2 dashboards, KV-store schema, RBA integration) | S4 | 8–10 |
| EPIC-10 | Eval harness + synthetic data generator (mirrors DNS Guard's `Syntethic-Data/` sibling-folder convention) | Cross-cutting | 4–5 |
| EPIC-11 | Demo video assets + README + architecture diagrams (light+dark PNG mirroring DNS Guard's pattern) | Cross-cutting | 3 |
| EPIC-12 | AppInspect compliance hardening + optional Splunkbase submission prep | Cross-cutting | 2–3 |

**Total: ~50–60 stories.**

## Repo layout (the spine of `docs/architecture.md` "File structure" section)

Target after first code lands. Specs describe this; spec-writer encodes it; agents implement against it.

```
aegis/
├── README.md
├── LICENSE                                  # Apache-2.0
├── .gitignore
├── .github/
│   ├── workflows/                           # CI/CD per docs/cicd-spec.md
│   │   ├── ci.yml                           # build + test + lint + 400-LOC + AppInspect
│   │   ├── eval.yml                         # eval harness on PR + nightly
│   │   ├── release.yml                      # tag-triggered signed release
│   │   └── security.yml                     # pip-audit + gitleaks + trivy
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── pyproject.toml                           # uv-managed Python monorepo
├── uv.lock
├── docs/                                    # all specs land here
│   ├── PRD.md
│   ├── architecture.md
│   ├── cicd-spec.md
│   ├── eval-spec.md
│   ├── ux-spec.md
│   ├── epics.md
│   ├── stories/
│   └── plans/2026-06-02-aegis-spec-set-design.md
├── packages/
│   ├── aegis_core/                          # shared domain types — used by everything
│   │   ├── pyproject.toml
│   │   ├── src/aegis_core/
│   │   │   ├── verdict.py                   # Verdict, Severity, etc.
│   │   │   ├── otel.py                      # gen_ai.evaluation.result emitter
│   │   │   ├── errors.py
│   │   │   └── ...
│   │   └── tests/
│   ├── aegis_judges/                        # judgment-layer clients
│   │   ├── pyproject.toml
│   │   ├── src/aegis_judges/
│   │   │   ├── ai_defense.py                # Cisco AI Defense Inspection API client
│   │   │   ├── foundation_sec.py            # |ai SPL invocation client (explainer)
│   │   │   ├── defenseclaw_backend.py       # fallback regex backend via DefenseClaw
│   │   │   ├── luna2_client.py              # future plug-in (stub)
│   │   │   └── ...
│   │   └── tests/
│   ├── aegis_mw/                            # Surface 1 — middleware library
│   │   ├── pyproject.toml
│   │   ├── src/aegis_mw/
│   │   │   ├── tool_middleware.py
│   │   │   ├── model_middleware.py
│   │   │   ├── subagent_middleware.py
│   │   │   ├── agent_middleware.py
│   │   │   └── ...
│   │   └── tests/
│   └── aegis_mcp/                           # Surface 2 — own MCP server
│       ├── pyproject.toml
│       ├── src/aegis_mcp/
│       │   ├── server.py                    # FastMCP / mcp-python registration
│       │   ├── tools/
│       │   │   ├── score_prompt_injection.py
│       │   │   ├── judge_tool_call.py
│       │   │   ├── check_output_leak.py
│       │   │   └── audit_trace.py
│       │   └── schemas.py                   # MCP outputSchema definitions
│       └── tests/
├── splunk_apps/
│   └── aegis_app/                           # Surface 4 — Splunk app
│       ├── README                           # required for Splunkbase
│       ├── default/
│       │   ├── app.conf
│       │   ├── savedsearches.conf
│       │   ├── transforms.conf
│       │   ├── props.conf
│       │   ├── macros.conf
│       │   ├── risk_factors.conf            # ES RBA integration
│       │   ├── collections.conf             # KV-store schemas
│       │   ├── alert_actions.conf
│       │   └── data/ui/views/
│       │       ├── agent_risk_overview.xml  # Dashboard Studio v2
│       │       ├── verdict_inspector.xml
│       │       └── regulator_evidence_pack.xml
│       ├── lookups/
│       ├── metadata/default.meta
│       ├── static/
│       │   ├── appIcon.png
│       │   └── appIconAlt.png
│       └── .appinspect.expect.yaml
├── integrations/
│   └── defenseclaw/                         # Surface 3 — config delta + docs
│       ├── README.md                        # how to point DefenseClaw at our Splunk index
│       ├── examples/defenseclaw.yaml        # config example
│       └── upstream-pr-notes.md             # notes for the contribute-back PR
├── Synthetic-Data/                          # mirrors DNS Guard's exact convention (typo and all)
│   ├── generate_agent_verdicts.py
│   ├── jailbreak_corpus/
│   └── pii_leak_corpus/
└── eval/
    ├── pyproject.toml
    ├── src/aegis_eval/
    │   ├── jailbreakbench.py
    │   ├── advbench.py
    │   ├── synthetic.py
    │   ├── metrics.py                       # precision/recall/F1/ECE/latency
    │   └── baselines/
    │       ├── defenseclaw_regex_only.py
    │       ├── gpt_oss_120b_judge.py
    │       └── ai_defense_alone.py
    └── tests/
```

## Library choices (the spine of `docs/architecture.md` "Library choices" section)

Every choice grounded in the verified domain knowledge. Justifications live in `docs/architecture.md`.

### Python runtime
- **Python 3.13+** — matches `splunk-sdk-python` 3.0.0 hard requirement (verified at `context/02-agent-frameworks/06-splunklib-ai-deep-read.md`).

### Package management
- **uv** — modern, fast, lockfile-first, monorepo-friendly. Already used by Splunk's own example apps.

### Web framework / MCP server
- **Official `mcp` Python SDK** (`pip install mcp`) — Anthropic's reference implementation. MCP spec 2025-11-25 stable per `context/10-standards/01-mcp-spec-deep.md`.

### LLM tool framework dependency surface
- **LangChain v1** — `splunklib.ai` runs entirely on LangChain v1 (verified at `splunklib/ai/core/backend_registry.py:18-24`). Aegis-MW transitively requires it; pinned in Surface 1's `pyproject.toml`.

### HTTP client
- **httpx** — async + sync, used by `splunklib.ai` itself. Note: `splunklib/ai/tools.py:308` has `verify=False` for Splunk MCP Server connections; document but don't replicate that.

### OpenTelemetry
- **opentelemetry-api**, **opentelemetry-sdk**, **opentelemetry-util-genai** — per OTel GenAI semantic conventions 2026-06 (55 attributes, 0 deprecated; `gen_ai.evaluation.result` event verified).

### Validation
- **pydantic v2** — for `Verdict`, MCP `outputSchema`, AI Defense client request/response types.

### Testing
- **pytest** + **pytest-asyncio** + **hypothesis** (property-based tests for verdict shape invariants) + **respx** (httpx mocking).

### Linting / formatting / typing
- **ruff** (replaces black + isort + flake8 + pyupgrade)
- **mypy --strict** for `aegis_core` and `aegis_judges` (highest invariant load)
- **pre-commit** for hooks including 400-LOC enforcement

### Splunk app build / validation
- **splunk-appinspect** (PyPI; AppInspect 4.2.1 per `context/06-splunk-ai-stack/`) — required for Splunkbase + Splunk Cloud private-app install.

### CI/CD
- **GitHub Actions** — matches Splunk's own example repos; free for public repos; well-integrated with Anthropic / OpenAI agentic tools.

### Eval datasets
- **JailbreakBench** (`pip install jailbreakbench`)
- **AdvBench** — from `llm-attacks/llm-attacks` repo (cloned in `inspiration/`)
- **Custom synthetic corpus** in `Synthetic-Data/` (per DNS Guard pattern)

### Dependencies on Cisco tools
- **Cisco AI Defense Inspection API** — typed Python client built in `aegis_judges/ai_defense.py`. Mockable for tests via `respx`. Live API access gated to Cisco Security Cloud Control tenants per `context/sources/docs-saved/abu-followup-2026-06-02.md`.
- **DefenseClaw** (Apache-2.0) — depend, don't rebuild. Config delta in `integrations/defenseclaw/`. Upstream PR plans tracked.

## What's deliberately NOT in v1

These are explicit non-goals captured here so future agents don't widen scope mid-build:

1. **No standalone CISO webapp.** Dashboard Studio v2 inside Splunk is the CISO UI. No React app, no Next.js, no separate web service.
2. **No FedRAMP-compatible deployment in v1.** Splunk Hosted Models is AWS commercial only; Cisco AI Defense is not FedRAMP. Future work.
3. **No commitment to a Luna-2 Splunk integration date.** Patrick Lin's May 28 2026 Splunk blog uses future tense; no announced date. Luna-2 is referenced as a future plug-in, not a v1 dependency.
4. **No replacement of `splunklib/ai/security.py`'s 9-regex baseline.** We call into it as a cheap first-pass classifier and escalate ambiguous cases.
5. **No FastMCP-vs-mcp-Python-SDK debate** in spec phase — locked to official `mcp` Python SDK. Re-evaluation deferred to first refactor.
6. **No multi-tenant deployment in v1.** Single-tenant per Splunk instance; multi-tenant is future work.
7. **No SOAR playbook generation in v1.** Aegis emits HEC events; ES correlation searches + existing SOAR custom functions consume them. Aegis does not author playbooks.

## Sanity-check on the 5 known blockers from prior research

For each, the spec set's resolution:

| Blocker | Resolution in spec |
|---|---|
| Exact `\| ai` SPL provider/model values for Foundation-Sec | `aegis_judges/foundation_sec.py` ships with a configurable provider/model interface; first integration test sets it via env var; documented in `docs/cicd-spec.md` as a Day-0 install step against Abu's Splunk Cloud trial. |
| Hosted-models dev-license access confirmation | Spec ships with **mock-first** Foundation-Sec client. Real-vs-mock toggled by env var. Story `EPIC-05` includes "verify against live Cloud trial" gate. |
| Splunk MCP Server v1.2.0 TGZ actual contents | **Not a blocker for us** — Aegis MCP Server is parallel, not into Splunk's. Documented in `docs/architecture.md`. |
| AI Agent Monitoring platform-side judge LLM name | **Not a blocker** — Aegis emits OTel GenAI events that AI Agent Monitoring auto-ingests; the platform-side judge runs in parallel, not in our path. |
| Cisco AI Defense free dev trial | Spec ships with DefenseClaw-regex-backend as fallback judge. Explorer Edition (`https://explorer.aidefense.cisco.com/`) for demo recordings. Live Inspection API integration story (`EPIC-04-S-04`) is gated on credentials and has a `mock=true` default. |

Net: **zero hard blockers.** All spec writing can proceed.

## Process — what happens after this brainstorm doc

1. **Now:** invoke `sahil-spec-writer` with this design as input + `13-architecture-recommendation-v2.md` + `context/` folder.
2. Spec writer produces `docs/PRD.md` + `docs/architecture.md` + `docs/cicd-spec.md` + `docs/eval-spec.md` + `docs/ux-spec.md` + `docs/epics.md` + `docs/stories/*.md` in one pass.
3. Abu reviews; signs off OR requests revisions.
4. **After approval:** `gh repo create` + push specs + create issues from stories using `gh issue create` (one issue per story).
5. **After issues are live:** `sahil-hackathon-orchestrator` fires per-ticket coding agents.

## Approval

Approved by Abu on 2026-06-02 via AskUserQuestion. License: Apache-2.0. Project name: Aegis. Scope: full one-pass. Location: `workspace/aegis/`.

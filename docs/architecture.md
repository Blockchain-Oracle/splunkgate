# Architecture — Aegis

**Status:** DRAFT (locks after Abu approval — no architecture changes post-approval without Abu sign-off + ADR)
**Last updated:** 2026-06-02
**Architecture source of truth:** `../research/splunk-agentic-ops-2026/13-architecture-recommendation-v2.md`
**Hallucination audit:** `../context/HALLUCINATION-AUDIT.md`

---

## Stack (locked)

| Layer | Choice | Version | Justification (context citation) |
|---|---|---|---|
| **Language** | Python | 3.13+ | splunk-sdk-python 3.0.0 hard-requires Python 3.13 (`context/02-agent-frameworks/06-splunklib-ai-deep-read.md`) |
| **Package manager** | uv | latest | Modern lockfile-first; monorepo-friendly; used by Splunk example apps |
| **Validation** | pydantic | v2 | Verdict / MCP outputSchema / AI Defense request-response types |
| **HTTP client** | httpx | latest | Async + sync; used by splunklib.ai itself. NOTE: `splunklib/ai/tools.py:308` has `verify=False` for Splunk MCP — document, do not replicate |
| **MCP runtime** | Official `mcp` Python SDK | latest | Anthropic's reference impl; MCP spec 2025-11-25 Stable (`context/10-standards/01-mcp-spec-deep.md`) |
| **LangChain (transitive)** | v1 | latest | `splunklib.ai` runs entirely on LangChain v1 (`backend_registry.py:18-24` hardcodes `langchain_backend_factory`). Aegis-MW transitively requires it |
| **OTel** | opentelemetry-api/sdk, opentelemetry-util-genai | latest | 55 `gen_ai.*` attributes, 0 deprecated; `gen_ai.evaluation.result` event with `name`/`score.value`/`score.label`/`explanation` slots (`context/10-standards/02-otel-genai-semantic-conventions.md`) |
| **Test runner** | pytest | latest | + pytest-asyncio for async, hypothesis for property tests, respx for httpx mocking |
| **Lint/format** | ruff | latest | Replaces black + isort + flake8 + pyupgrade |
| **Type checker** | mypy | latest | `--strict` for `aegis_core` + `aegis_judges`; non-strict acceptable for `aegis_app` (Splunk app Python is constrained) |
| **Pre-commit** | pre-commit | latest | Hooks: ruff, mypy, 400-LOC check, no-secret, yaml-lint |
| **CI** | GitHub Actions | n/a | Matches Splunk example repos; free for public; well-integrated with agentic tooling |
| **Splunk app validator** | splunk-appinspect | 4.2.1+ | Required for Splunkbase + Splunk Cloud private-app install (`context/05-splunk-core/09-appinspect.md`) |
| **Eval datasets** | jailbreakbench (PyPI), llm-attacks/llm-attacks (git submodule), Synthetic-Data/ (in-repo) | n/a | Per `context/01-threat-landscape/02-jailbreak-techniques.md` + Imprompter PDF |
| **Splunk Cloud target** | Version 10.4.2604.5 verified at Abu's instance | n/a | `context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md` |

---

## Repo structure (monorepo)

```
aegis/
├── README.md
├── LICENSE                                          # Apache-2.0
├── .gitignore
├── architecture_diagram.png                         # Required at root per Devpost submission (story-readme-04)
├── architecture_diagram_dark.png                    # Light + dark variants (DNS Guard pattern)
├── pyproject.toml                                   # uv workspace root
├── uv.lock
├── .python-version                                  # 3.13
├── .pre-commit-config.yaml
├── .ruff.toml
├── mypy.ini
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                                   # build + test + lint + 400-LOC + AppInspect
│   │   ├── eval.yml                                 # eval harness on PR + nightly
│   │   ├── release.yml                              # tag-triggered signed release
│   │   └── security.yml                             # pip-audit + gitleaks + trivy
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── story.md
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/                                            # all specs land here
│   ├── PRD.md
│   ├── architecture.md
│   ├── cicd-spec.md
│   ├── eval-spec.md
│   ├── ux-spec.md
│   ├── epics.md
│   ├── sprint-status.yaml
│   ├── stories/                                     # ~50-60 story files
│   ├── plans/
│   │   └── 2026-06-02-aegis-spec-set-design.md
│   └── adrs/                                        # post-build architecture decisions
├── packages/
│   ├── aegis_core/                                  # shared domain types — used by everything
│   │   ├── pyproject.toml
│   │   ├── src/aegis_core/
│   │   │   ├── __init__.py
│   │   │   ├── verdict.py                           # Verdict, Severity, VerdictLabel
│   │   │   ├── otel.py                              # gen_ai.evaluation.result emitter
│   │   │   ├── errors.py
│   │   │   └── trace.py                             # trace_id propagation
│   │   └── tests/
│   ├── aegis_judges/                                # judgment-layer clients
│   │   ├── pyproject.toml
│   │   ├── src/aegis_judges/
│   │   │   ├── __init__.py
│   │   │   ├── ai_defense.py                        # Cisco AI Defense Inspection API client
│   │   │   ├── ai_defense_mock.py                   # respx-based mock (dev default)
│   │   │   ├── foundation_sec.py                    # |ai SPL invocation client (explainer)
│   │   │   ├── defenseclaw_backend.py               # fallback regex backend via DefenseClaw rules
│   │   │   ├── luna2_client.py                      # future plug-in (stub returning NotImplementedError)
│   │   │   └── splunklib_security_fallback.py       # calls splunklib.ai.security.detect_injection as cheap first-pass
│   │   └── tests/
│   ├── aegis_mw/                                    # Surface 1 — middleware library for splunklib.ai
│   │   ├── pyproject.toml
│   │   ├── src/aegis_mw/
│   │   │   ├── __init__.py
│   │   │   ├── tool_middleware.py
│   │   │   ├── model_middleware.py
│   │   │   ├── subagent_middleware.py
│   │   │   ├── agent_middleware.py
│   │   │   ├── profiles.py                          # FSI / HIPAA / PubSec preset judging chains
│   │   │   └── config.py
│   │   ├── examples/
│   │   │   └── support_agent.py                     # 30-line demo agent for the README + demo video
│   │   └── tests/
│   └── aegis_mcp/                                   # Surface 2 — own MCP server
│       ├── pyproject.toml
│       ├── src/aegis_mcp/
│       │   ├── __init__.py
│       │   ├── server.py                            # mcp-python registration
│       │   ├── schemas.py                           # MCP outputSchema (Pydantic → JSON Schema)
│       │   └── tools/
│       │       ├── score_prompt_injection.py
│       │       ├── judge_tool_call.py
│       │       ├── check_output_leak.py
│       │       └── audit_trace.py
│       └── tests/
├── splunk_apps/
│   └── aegis_app/                                   # Surface 4 — Splunk app
│       ├── README                                   # required for Splunkbase
│       ├── default/
│       │   ├── app.conf
│       │   ├── savedsearches.conf
│       │   ├── transforms.conf
│       │   ├── props.conf
│       │   ├── macros.conf                          # MLTK macros (DNS Guard pattern: fit DensityFunction, fit KMeans k=2, anomalydetection)
│       │   ├── risk_factors.conf                    # ES RBA integration
│       │   ├── collections.conf                     # KV-store schemas for verdict history
│       │   ├── alert_actions.conf
│       │   ├── eventtypes.conf
│       │   ├── tags.conf
│       │   └── data/ui/views/
│       │       ├── agent_risk_overview.xml          # Dashboard Studio v2 JSON-in-XML
│       │       ├── verdict_inspector.xml
│       │       └── regulator_evidence_pack.xml
│       ├── lookups/
│       │   ├── risk_profile_fsi.csv
│       │   ├── risk_profile_hipaa.csv
│       │   └── risk_profile_pubsec.csv
│       ├── metadata/default.meta
│       ├── static/
│       │   ├── appIcon.png
│       │   ├── appIconAlt.png
│       │   ├── appIcon_2x.png
│       │   └── appIconAlt_2x.png
│       └── .appinspect.expect.yaml                  # mirrors CIMplicity's pattern (25 manual checks list)
├── integrations/
│   └── defenseclaw/                                 # Surface 3 — config delta + docs
│       ├── README.md                                # how to point DefenseClaw at our Splunk index
│       ├── examples/defenseclaw.yaml                # config example
│       └── upstream-pr-notes.md                     # notes for contribute-back PR
├── Synthetic-Data/                                  # mirrors DNS Guard exact convention (typo preserved)
│   ├── README.md
│   ├── generate_agent_verdicts.py
│   ├── jailbreak_corpus/
│   │   ├── jailbreakbench_subset.jsonl
│   │   ├── advbench_subset.jsonl
│   │   └── manual_curated.jsonl
│   └── pii_leak_corpus/
│       └── imprompter_payloads.jsonl
└── eval/
    ├── pyproject.toml
    ├── src/aegis_eval/
    │   ├── __init__.py
    │   ├── jailbreakbench.py
    │   ├── advbench.py
    │   ├── synthetic.py
    │   ├── metrics.py                               # precision/recall/F1/ECE/latency
    │   └── baselines/
    │       ├── __init__.py
    │       ├── defenseclaw_regex_only.py
    │       ├── gpt_oss_120b_judge.py
    │       └── ai_defense_alone.py
    └── tests/
```

---

## Coding standards (enforced via pre-commit + CI fail-on-exceed)

### Hard rules

1. **Every source file ≤ 400 LOC** (excluding blank lines + pure comments). Enforced by `.pre-commit-hooks/check_loc.py` and by CI fail-on-exceed. If a file approaches 400 LOC, split it via composition or extraction. No exceptions.
2. **`mypy --strict` clean** for `packages/aegis_core/` and `packages/aegis_judges/`. Non-strict acceptable for `packages/aegis_mw/`, `packages/aegis_mcp/`, `splunk_apps/aegis_app/bin/`.
3. **ruff clean** across the entire monorepo (config: line-length 100, all rules enabled except E501 deferred to formatter).
4. **All tests pass** — `uv run pytest` returns 0 across all packages.
5. **No real Cisco API credentials in code or fixtures.** AI Defense client must default to `mock=True` in tests; `mock=False` requires `AEGIS_AI_DEFENSE_API_KEY` env var.
6. **No real Splunk credentials in code or fixtures.** Splunk integration tests gated on `AEGIS_SPLUNK_HEC_TOKEN` env var.
7. **No `verify=False` HTTP calls in production code paths.** `splunklib/ai/tools.py:308`'s `verify=False` is documented but never replicated. If self-signed cert is needed for dev, use `AEGIS_DEV_INSECURE_TLS=1` env var with explicit warning log on startup.

### Soft rules (best practices)

- Async by default for I/O; sync only for in-process pure functions.
- All public functions get a docstring (numpy / Google style — picked in ADR-002).
- All public classes / functions get a Pydantic-validated input model.
- All errors raised are subclasses of `aegis_core.errors.AegisError`.
- All log lines use `structlog` with stable key names (`event`, `verdict`, `severity`, `trace_id`, …).
- All test files use `respx` for httpx mocking; no `unittest.mock` for HTTP.

---

## Required external libraries (use these — do not reinvent)

The coding agent MUST use these. Do not build from scratch what a library already solves.

| Library | Purpose | How to add | Context citation |
|---|---|---|---|
| `splunk-sdk` 3.0.0+ | `splunklib.ai` middleware system (Surface 1) | `uv add splunk-sdk` | `context/02-agent-frameworks/06-splunklib-ai-deep-read.md` |
| `mcp` (Python SDK) | MCP server runtime (Surface 2) | `uv add mcp` | `context/10-standards/01-mcp-spec-deep.md` |
| `pydantic` v2 | Domain types, MCP outputSchema, AI Defense client | `uv add pydantic` | n/a |
| `httpx` | HTTP client for AI Defense + Foundation-Sec proxy calls | `uv add httpx` | n/a |
| `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-util-genai` | OTel emission (`gen_ai.evaluation.result`) | `uv add opentelemetry-api opentelemetry-sdk opentelemetry-util-genai` | `context/10-standards/02-otel-genai-semantic-conventions.md` |
| `structlog` | Structured logging | `uv add structlog` | n/a |
| `tenacity` | Retry / circuit breaker for AI Defense client | `uv add tenacity` | n/a |
| `pytest` + `pytest-asyncio` + `hypothesis` + `respx` | Tests | `uv add --dev pytest pytest-asyncio hypothesis respx` | n/a |
| `ruff` | Lint + format | `uv add --dev ruff` | n/a |
| `mypy` | Strict typing | `uv add --dev mypy` | n/a |
| `splunk-appinspect` | Splunk app validator | `uv add --dev splunk-appinspect` | `context/05-splunk-core/09-appinspect.md` |
| `jailbreakbench` | Eval dataset | `uv add --dev jailbreakbench` | `context/01-threat-landscape/02-jailbreak-techniques.md` |
| `defenseclaw` (Go dependency) | Surface 3 — depend, don't rebuild | Documented integration, no Python install | `context/HALLUCINATION-AUDIT.md` H-44/H-45 |

**Banned (do not add):**
- `requests` — use `httpx`
- `flask`, `django`, `fastapi` for the MCP server — use the official `mcp` SDK
- `numpy`/`pandas` in `aegis_core` or `aegis_judges` — too heavy for tight runtime path; eval-only

### Context7 library research rule (mandatory)

Before implementing anything from scratch:

```bash
# Step 1: find the library
mcp__context7__resolve-library-id libraryName="<what you need>"

# Step 2: read the docs
mcp__context7__query-docs context7CompatibleLibraryID="<id>" topic="<specific area>" tokens=5000
```

If a library exists that solves it, use it. Do not build it yourself.

Applies to: HTTP retries, circuit breakers, MCP protocol primitives, OTel emission, Pydantic schema generation, structured logging, AppInspect rules.

---

## API schemas

### Verdict (the type every surface emits)

```python
# packages/aegis_core/src/aegis_core/verdict.py

from enum import Enum
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID

class Severity(str, Enum):
    NONE_SEVERITY = "NONE_SEVERITY"   # matches Cisco AI Defense response enum
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class VerdictLabel(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    MODIFY = "MODIFY"
    REVIEW = "REVIEW"

class RuleHit(BaseModel):
    rule: str                                          # e.g., "Prompt Injection"
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]

class Verdict(BaseModel):
    trace_id: UUID
    timestamp: datetime
    verdict: VerdictLabel
    severity: Severity
    rules: list[RuleHit]                              # matches AI Defense response field name (not `triggered_rules`)
    explanation: str | None = None                    # Foundation-Sec-generated WHY-string
    classifications: list[str] = Field(default_factory=list)  # mirrors AI Defense response
    modifications: dict | None = None                  # for MODIFY verdicts: redactions, etc.
    surface: Literal["mw_model", "mw_tool", "mw_subagent", "mcp_score", "mcp_judge_tool", "mcp_check_output", "mcp_audit", "defenseclaw"]
    latency_ms: float
```

### OTel emission shape

Every verdict emits a `gen_ai.evaluation.result` event per `context/10-standards/02-otel-genai-semantic-conventions.md`:

```python
# Pseudo: aegis_core/otel.py
emit_event(
    name="gen_ai.evaluation.result",
    attributes={
        "gen_ai.evaluation.name": "aegis.safety_verdict",
        "gen_ai.evaluation.score.value": float(severity_to_score(verdict.severity)),
        "gen_ai.evaluation.score.label": verdict.verdict.value.lower(),   # "block" | "allow" | "modify" | "review"
        "gen_ai.evaluation.explanation": verdict.explanation,
        # MCP sub-convention if call originated from MCP:
        "mcp.method.name": "tools/call",
        "mcp.session.id": str(session_id),
        # Aegis custom (proposing upstream post-hackathon):
        "aegis.surface": verdict.surface,
        "aegis.rules": [r.rule for r in verdict.rules],
        "aegis.trace_id": str(verdict.trace_id),
    },
)
```

The OTel pipeline lands these in Splunk via HEC; Splunk's `props.conf` parses them into the `cisco_ai_defense:aegis_verdict` sourcetype to colocate with Cisco Security Cloud's AI Defense events.

### MCP outputSchema (Surface 2)

Every Aegis MCP tool returns a `Verdict` validated against this Pydantic-derived JSON Schema:

```python
# packages/aegis_mcp/src/aegis_mcp/schemas.py
VERDICT_OUTPUT_SCHEMA = Verdict.model_json_schema()
```

The MCP `structuredContent` field carries the verdict; protocol-level validation at the MCP server boundary catches schema drift (`context/10-standards/01-mcp-spec-deep.md`).

### Cisco AI Defense Inspection API client request / response

Per `context/07-cisco-stack/01-ai-defense-deep.md`:

```python
# packages/aegis_judges/src/aegis_judges/ai_defense.py — request/response models
class InspectRequest(BaseModel):
    text: str
    rules_enabled: list[str] | None = None   # subset of the 11 named rules
    metadata: dict | None = None

class InspectResponse(BaseModel):
    is_safe: bool
    severity: Severity                        # includes NONE_SEVERITY
    classifications: list[str]
    rules: list[str]                          # NOT triggered_rules
    explanation: str
```

Auth: header `X-Cisco-AI-Defense-API-Key: <key>`. Regional endpoints `us.api.inspect.aidefense.security.cisco.com`, `ap.…`, `eu.…`.

---

## Banned patterns

- `from-purple-500 to-pink-500` Tailwind gradient — N/A (we don't ship a web UI in v1, but if anyone tries adding one)
- Hardcoded mock data in hot path — AI Defense client toggles via env var; mocks are test-only
- `requests` library — use `httpx`
- `verify=False` in production code paths (see hard rules)
- `print()` for logs — use `structlog`
- `unittest.mock` for HTTP — use `respx`
- `try/except: pass` — always re-raise as `AegisError` subclass
- `# type: ignore` without an inline justification comment
- `Any` type annotations in `aegis_core` or `aegis_judges` (strict mode catches this)
- Foundation-Sec invocation as a classifier (verified incorrect usage; explainer only)
- Registering tools into Splunk's official MCP Server (impossible — CiscoDevNet repo is README only)

---

## Architecture decisions (ADRs)

**ADR-001 — uv over poetry/pdm.** Lockfile-first, fast, monorepo-friendly. Splunk's official splunk-sdk-python README uses it.

**ADR-002 — Multi-package monorepo via uv workspaces (over separate repos).** Shared `aegis_core` is touched by every surface; one PR can land cross-surface changes; single CI pipeline; one place for the eval harness to import everything.

**ADR-003 — Foundation-Sec as explainer, NOT as classifier.** Three independent context audits (R5, R7, R12) verified that Cisco markets and deploys Foundation-Sec as a generator (security copilot). Using it as a binary classifier would be off-label. Aegis uses it only to generate human-readable explanations of WHY a verdict was reached; Cisco AI Defense Inspection API handles binary classification.

**ADR-004 — Our own MCP server (Surface 2) running parallel to Splunk's, NOT registering into Splunk's.** Splunk's MCP Server is closed-source (`CiscoDevNet/Splunk-MCP-Server-official` is README+LICENSE only — multi-confirmed). Aegis MCP exposes `sentinel_*` and `aegis_*` tool names; Splunk's `splunk_*` and `saia_*` tools coexist via standard MCP client multi-server configs.

**ADR-005 — Aegis events emit to `cisco_ai_defense:aegis_verdict` sourcetype.** Cisco Security Cloud app 7404 v3.6.6 (Cisco Systems, 55K installs) populates `cisco_ai_defense:*` sourcetypes. Colocating Aegis events in the same namespace gives SOC analysts unified search without schema migration. Verified live via Abu's Splunk Cloud instance on 2026-06-02.

**ADR-006 — Default to AI Defense mock client; live calls gated on env var.** Cisco AI Defense Inspection API access requires Cisco Security Cloud Control tenant + AI Defense license (`context/sources/docs-saved/abu-followup-2026-06-02.md`). Mock-first lets the entire test suite run without credentials; live-toggled paths run in nightly eval and against Abu's Explorer Edition (`https://explorer.aidefense.cisco.com/`) for demo recordings.

**ADR-007 — Luna-2 ships as `NotImplementedError`-raising stub.** Cisco closed the Galileo acquisition 2026-05-22 (verified via Cisco SEC Form S-8 Ex-99.2). Patrick Lin's May 28 2026 Splunk blog uses future tense ("will integrate") with no committed date. Stub client documents the future plug-in shape so adoption is one PR away when Cisco publishes the SDK.

**ADR-008 — Splunk app uses Classic Simple XML wrapper around Dashboard Studio v2 JSON-in-XML.** Per `context/11-prior-art/01-build-a-thon-2025-deep-read.md`, the DNS Guard 1st-place winner used this exact pattern. Dashboard Studio v2 dashboards are JSON inside `<dashboard>` XML.

**ADR-009 — pre-commit hook + CI fail-on-exceed for the 400-LOC rule.** Two layers — local pre-commit catches before push; CI catches if pre-commit is bypassed. Failure message points the contributor to the file + line count + suggested split.

**ADR-010 — splunklib.ai's 9-regex `detect_injection` is the cheap first-pass classifier.** Calling into it (rather than replacing it) leverages Splunk's own work, keeps the cheap path cheap, and only escalates ambiguous cases to AI Defense + Foundation-Sec. `context/02-agent-frameworks/06-splunklib-ai-deep-read.md` quotes all 9 regex patterns verbatim.

**ADR-011 — `Synthetic-Data/` folder name uses corrected spelling.** DNS Guard 2025 winner used `Syntethic-Data/` (sic — a typo). We deliberately use the corrected `Synthetic-Data/` because (a) the typo would confuse coding agents during shell verification with copy-paste paths, (b) folder name is dev-facing only, (c) judges read the README + dashboards, not folder names. The DNS Guard pattern we mirror is the *content* (Python data generator in a sibling folder, generating synthetic events for eval) — not the misspelling.

---

## CI requirements

Defined in detail in `cicd-spec.md`. Headline requirements:

- All CI checks must be green before any PR merges. Never merge while CI is red.
- The CI pipeline runs on every push to any branch and on every PR open/update.
- Required green checks before merge to `main`: `lint`, `typecheck`, `test`, `loc-cap`, `appinspect`, `eval-smoke`, `security`.

See `docs/cicd-spec.md` for the YAML.

---

## Submission checklist gates

The build is "done" only when each box is checked. The coding agent verifies all of these before submitting:

### Hackathon submission requirements (`context/01-prizes-tracks.md`)
- [ ] Architecture diagram `architecture_diagram.png` (or `.md` / `.pdf`) at repo root
- [ ] Demo video < 3 min on YouTube
- [ ] Public GitHub repo with Apache-2.0 license (auto-detectable by GitHub)
- [ ] README has install + run instructions
- [ ] Project demonstrates use of Splunk Hosted Models (Foundation-Sec via `| ai`)
- [ ] Project uses Splunk MCP Server (our own, alongside theirs)

### Aegis-specific gates
- [ ] `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_judges/src/` returns zero unjustified hits in production code paths (test fixtures and `*_mock.py` files are §14 carve-outs)
- [ ] `find . -name '*.py' -not -path '*/.venv/*' -not -path '*/node_modules/*' | xargs wc -l | awk '$1 > 400 { print }'` returns nothing (400-LOC gate)
- [ ] `splunk-appinspect inspect splunk_apps/aegis_app/` passes with zero `error`-severity findings; manual checks documented in `.appinspect.expect.yaml`
- [ ] Eval table generated; `eval/results/latest/summary.md` exists with precision/recall/F1/ECE per evaluator
- [ ] No real API keys committed; `gitleaks scan` returns clean

### README shape (§13)
- [ ] `README.md` has: title, one-line pitch, banner image, demo video link, architecture diagram, install steps, eval table, license
- [ ] `LICENSE` file present (Apache-2.0)
- [ ] Demo video link is a real YouTube URL (not a placeholder)
- [ ] Multiple commits showing iteration (not one giant "initial commit")
- [ ] Credits MCP Watch, Cisco Security Cloud, DefenseClaw, splunklib.ai, NeMo Guardrails

### CI
- [ ] `.github/workflows/{ci,eval,release,security}.yml` exist and pass on main branch
- [ ] `uv run pytest` runs ≥ 200 behavioral test cases across packages

---

## Open architectural questions (post-build research)

These are tracked separately so they don't block the build:

1. `splunklib.ai` Conversation Store sharing across surfaces — does S1's per-agent conversation store leak into S2's per-MCP-session state? Investigate first time we have parallel S1 + S2 traffic.
2. AGNTCY MCE plugin shape — could `aegis_eval` post-hoc batches register as MCE plugin so they appear in Splunk AI Agent Monitoring's metrics tab? (Confirmed exists per R10; not blocking v1.)
3. OTel GenAI upstream proposal — what's the SIG's appetite for adding `score.label = "block" | "unsafe"` enum values? Propose post-hackathon.

---

## File-level references back into `context/`

Every load-bearing claim in this spec maps back to a primary-source-grounded fact in `context/`. The orchestrator-spawned coding agents pulling stories from this spec MUST cite the same `context/` files in their PR descriptions. Pattern: `Per context/<folder>/<file>.md §<section>:`. Bare assertions without citations get blocked by `sahil-pr-audit`.

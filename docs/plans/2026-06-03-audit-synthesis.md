# Spec Audit Synthesis — Consolidated Fix Plan

**Date:** 2026-06-03
**Inputs:** 5 audit reports
- `2026-06-03-spec-audit-cross-spec.md` (6 critical, 8 minor)
- `2026-06-03-spec-audit-stories-A.md` (7 critical, 13 minor)
- `2026-06-03-spec-audit-stories-B.md` (8 critical, 17 minor)
- `2026-06-03-spec-audit-stories-C.md` (7 critical, 18 minor)
- `2026-06-03-spec-audit-goal-coverage.md` (4 critical, 7 minor)

**Headline:** 32 raw critical findings. After de-dup ≈ 24 unique critical issues. Fixable in one consolidated pass.

**Process gate:** No GitHub issue closed and no orchestrator dispatch until these fixes land.

---

## Block A — Mechanical / textual fixes (Edit + sed)

| # | Issue | Files | Fix |
|---|---|---|---|
| A-1 | Broken `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md` reference (file lives in `research/`, not `context/`) | PRD.md, architecture.md, epics.md, story-readme-01, story-readme-02, story-demo-01 (21 occurrences total) | sed: `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md` → `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md` |
| A-2 | "Sentinel" codename leftover (project name is SplunkGate) | architecture.md:369 (ADR-004), story-mcp-01:134 | Replace `sentinel_*` → `splunkgate_*` in tool-name discussion; ADR-004 prose update |
| A-3 | `Synthetic-Data` spelling self-contradiction | eval-spec.md:202, story-eval-01:23/166 | eval-spec.md drop "typo preserved" claim; story-eval-01 align to corrected spelling per ADR-011 |
| A-4 | PRD references non-existent story file name | PRD.md:65 | `story-readme-01-headline.md` → `story-readme-01-headline-and-banner-and-credits.md` |
| A-5 | `foundation_sec_classifier` literal in `RuleHit.source` enum contradicts ADR-003 | architecture.md:270 | Remove `"foundation_sec_classifier"` from the Literal type union; replace docstring to clarify Foundation-Sec only emits `explanation` field, not `RuleHit` |
| A-6 | Cisco AI Defense rule names hallucinated | story-app-05 (heatmap Y-axis), story-app-08 (risk_factors.conf × 4 spots) | Replace `Toxicity`/`Self-Harm`/`Violence` with the verbatim 11-rule list from PRD §92: `Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats` |
| A-7 | Splunkbase artifact extension drift | story-app-12 uses `.tar.gz`, story-cicd-08 uses `.tgz` | Standardize on `.tgz` everywhere (Splunkbase convention per `context/05-splunk-core/09-appinspect.md`) |
| A-8 | README credit count drift | story-readme-01 (PRD §13 names 5 incumbents; BDD #8 greps for 6-7; shell verify iterates 7) | Standardize on the 5 PRD-named incumbents + 2 additional (MCP Watch, Cisco Security Cloud) = 7; update PRD §13 to match |
| A-9 | Stale "surface=defenseclaw is wrong" artifact | story-eval-04:25 | Delete the artifact comment |
| A-10 | Drill-down contract drift | story-app-05 uses `form.rule=…`; story-app-06 declares input `input_rule` | Standardize on `form.rule` (single Splunk Dashboard Studio v2 convention); update story-app-06 |
| A-11 | `mypy.ini` parsing with `configparser` will hit `InterpolationSyntaxError` due to `*` in section names | story-skel-02 BDD criterion | Specify `RawConfigParser` in the BDD command |
| A-12 | `awk` pattern with quadruple-backtick escape broken under zsh | story-dc-02 | Replace with a Python one-liner equivalent |
| A-13 | `mcp-02` invents `splunkgate_judges.splunklib_security_fallback` module | story-mcp-02 | Replace with direct `from splunklib.ai.security import detect_injection` |

---

## Block B — Content corrections (Edit, semantic)

| # | Issue | Files | Fix |
|---|---|---|---|
| B-1 | Foundation-Sec API contract mismatch — caller and provider disagree on signature | story-mw-04 + story-mcp-05 call `splunkgate_judges.foundation_sec.explain(verdict, text)`; EPIC-05 ships `FoundationSecExplainer.explain(ctx: VerdictContext)`. story-mcp-05 also invents `run_search` which doesn't exist | Update story-mw-04 + story-mcp-05 to use the contract from EPIC-05 (`FoundationSecExplainer.explain(VerdictContext)`); add a `VerdictContext` Pydantic model to `splunkgate_core` if not already present |
| B-2 | `model_middleware.py` file-append split has structural seam ambiguity | story-mw-03 anchor sits inside ALLOW branch; story-mw-04 "insert at anchor" doesn't handle BLOCK (no post-scan should run) or MODIFY (which response gets post-scanned?) | Refactor: `story-mw-03` ships a `pre_inference_scan(...) -> Verdict` helper that always returns; `story-mw-04` ships a `post_inference_scan(response) -> Verdict` helper; the model_middleware function is a thin compose-via-explicit-handler-call that BOTH stories share via a registered hook table |
| B-3 | MCP `list_tools` test harness doesn't work against official mcp SDK FastMCP surface | story-mcp-01 through story-mcp-05 BDD tests | Add to `story-mcp-01`: a `list_tools_for_test()` test helper backed by the `register_tool` registry; downstream stories' BDD imports from there |
| B-4 | SplunkGate MCP never enumerates the Splunk `splunk_*` + `saia_*` tool names it coexists with | story-mcp-06 (Claude Desktop config docs) | Add a "Coexistence with Splunk MCP Server" section to story-mcp-06 enumerating the 10 `splunk_*` tools and 4 `saia_*` tools (verbatim from `context/06-splunk-ai-stack/03-splunk-mcp-server.md`) |
| B-5 | `docs/adrs/` directory in architecture.md:68 doesn't exist; no story creates it | architecture.md or story-skel-03 | Add to `story-skel-03`: create `docs/adrs/` + ADR template file (`docs/adrs/_template.md`) + README pointing future ADRs there |
| B-6 | PRD demo step 3 language says "before_model hook" — public API is `model_middleware` class wrap, not a hook function | PRD.md:79 (Demo moment step 3 console log) | Update prose to reference `model_middleware` instead of "before_model hook" |

---

## Block C — File-map ownership consolidation (EPIC-01 / EPIC-02)

Per batch-A finding A-C-01 through A-C-06. The cleanest fix:

| File | Old owners | New ownership |
|---|---|---|
| `pyproject.toml` (root, uv workspace) | cicd-01 NEW + skel-01 NEW | **skel-01 owns NEW**; cicd-01 references it as a precondition |
| `uv.lock` | cicd-01 NEW + skel-01 NEW | **skel-01 owns NEW**; cicd-01 only confirms it exists |
| `.python-version` | cicd-01 NEW + skel-01 NEW | **skel-01 owns NEW** |
| `packages/splunkgate_*/pyproject.toml` (×4) + `__init__.py` stubs (×4) | cicd-01 NEW + skel-01 NEW | **skel-01 owns NEW** |
| `eval/pyproject.toml` | cicd-01 NEW + cicd-06 NEW + skel-01 NEW (TRIPLE) | **skel-01 owns NEW**; cicd-01/cicd-06 UPDATE only as needed |
| `.pre-commit-config.yaml` | cicd-04 NEW (`check-loc` sh hook) + skel-04 NEW (`check-loc-400` py hook, different ID) | **cicd-04 owns NEW** with the canonical hook ID `check-loc-400` calling the `.py` script (script lives in cicd-03); skel-04 confirms install + adds the no-print hook |
| `splunk_apps/splunkgate_app/default/app.conf` + README | cicd-05 NEW (minimal shell for AppInspect job) + app-01 NEW (real shell) | **app-01 owns NEW**; cicd-05 picks up real shell as a precondition |
| **Dispatch order** | EPIC-01 before EPIC-02 in epics.md + sprint-status.yaml | **FLIP**: EPIC-02 (skel) before EPIC-01 (cicd) — workspace must exist before CI can use it |
| **Depends-on direction** | skel-01 depends_on cicd-01 | **FLIP**: cicd-01, cicd-02, cicd-06 depend_on skel-01 |

Also update `epics.md` dispatch queue to reflect the order flip.

---

## Block D — 6 new stories needed

| New story | Owns | Why |
|---|---|---|
| `story-app-13-synthetic-verdict-emitter-script.md` (EPIC-09) | `Synthetic-Data/scripts/emit_sample_verdict.py` | Orphaned dependency of app-02 + app-10; without it dashboards render empty + demo beat-1 has no data |
| `story-core-05-otel-hec-exporter-config.md` (EPIC-03) | `packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` + config | OTel → Splunk HEC bridge missing; architecture promise unverified |
| `story-eval-06-end-to-end-agent-to-splunk-integration.md` (EPIC-10) | `eval/scripts/e2e_demo.py` + asserts events land in Splunk via SPL | Demo dress-rehearsal gap; no story currently verifies the full path |
| `story-ops-01-branch-protection-config.md` (EPIC-12 or new EPIC-13) | `docs/ops/branch-protection.md` + `scripts/configure_branch_protection.sh` | cicd-spec.md requires it; no story configures it |
| `story-ops-02-github-secrets-and-adr-template.md` (EPIC-12 or new EPIC-13) | `docs/ops/secrets.md` + `gh secret set` wrappers + ADR template | Secrets-dependent jobs will silently skip/fail otherwise |
| `story-judges-06-defenseclaw-python-shim.md` (EPIC-04 or EPIC-08) | `packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py` | 3 stories (mw-02, mw-05, mcp-03) import it; no story creates it |

**Total: 60 → 66 stories.** Sprint-status.yaml + epics.md update needed.

---

## Block E — Coverage gaps (non-blocking, optional follow-up)

| Gap | Severity | Decision |
|---|---|---|
| PII/PHI/PCI ground-truth corpus has no dedicated story | minor | Fold into existing `story-eval-03` |
| `splunkgate_full_stack` callable in `report.py` has no owner | minor | Fold into existing `story-eval-05` |
| Splunk Cloud 10.4 compatibility not explicitly tested (Docker uses 9.4 floor) | minor | Document in `story-app-10` Notes; not worth a separate story |
| Sequential cross-story state dependencies (story-app-04 → app-03, app-08 → app-03, app-10 → app-02) | minor | Document in Notes sections; orchestrator handles via depends_on |

---

## Execution order

1. **Now (10 min):** Block A mechanical fixes via `sed` + targeted `Edit` calls
2. **Now (15 min):** Block B content corrections via `Edit`
3. **Now (15 min):** Block C file-map consolidation (4 stories rewritten; epics.md + sprint-status.yaml updated)
4. **Now (20 min):** Block D — 6 new story files written (sub-agent)
5. **Now (5 min):** Commit + push
6. **Now (10 min):** `gh issue edit` per affected story body
7. **Now (5 min):** Create 6 new GitHub issues from the 6 new story files
8. **Done.** Surface to Abu.

Total: ~80 minutes. All within this turn.

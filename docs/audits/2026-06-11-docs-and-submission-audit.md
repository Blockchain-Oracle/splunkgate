# Docs page + submission state audit — 2026-06-11

Two questions answered: (1) did we ship every docs section we said we would,
and did we improve on it; (2) what's the current state of every
Splunkbase submission gate.

## Part 1 — Docs page completeness

The designer prototype shipped 6 groups / 15 sections. The Next.js port at
`/docs` ships **6 groups / 19 sections** — every section the designer
designed is present, four new sections that the designer didn't include,
and the API signatures are now real (sourced from the repo, not
fabricated).

| Promised (designer) | Shipped | Notes |
|--|--|--|
| Get started — Overview | ✅ | Surface table + 1-pager intro |
| Get started — Quickstart | ✅ | Install → integrate → see-a-verdict path |
| Concepts — The Verdict type | ✅ | Real `EXAMPLE_VERDICT` (includes `modifications`); field table matches `packages/splunkgate_core/src/splunkgate_core/verdict.py` |
| Concepts — Severity & result | ✅ | Severity → OTel score mapping; enum pills |
| Concepts — The four surfaces | ✅ | Surface table with mw_model · mw_tool · mcp_judge_tool · etc. |
| Concepts — Judgment layer | ✅ | 3 models, each its real role; ADR-003 boundary called out |
| Integration — S1 Middleware | ✅ + EXPANDED | Classes table covers **all four** classes (SafetyModel / Tool / Subagent / Agent) — designer's prose only named three |
| Integration — S2 MCP server | ✅ + FIXED | Now names the **four real tools** (`splunkgate_score_prompt_injection`, `splunkgate_check_output_leak`, `splunkgate_judge_tool_call`, `splunkgate_audit_trace`). Designer prototype had a fabricated `splunkgate_judge_prompt`. |
| Integration — S3 DefenseClaw | ✅ | Config-delta YAML example |
| Integration — S4 Splunk app | ✅ | Install path, dashboards listed, AppInspect-clean note |
| Operations — OTel emission | ✅ | Real `gen_ai.evaluation.result` event body |
| Operations — HEC sourcetype | ✅ | Verbatim `cisco_ai_defense:splunkgate_verdict` |
| Operations — Failure modes | ✅ | Dependency-down behaviour table |
| Regulatory — NIST AI RMF | ✅ | GOVERN/MAP/MEASURE/MANAGE with SPL queries |
| Regulatory — SR 26-2 | ✅ | Verbatim footnote 3 quote |
| Regulatory — EU AI Act Art. 6 | ✅ | Penalty + record-keeping summary |
| Evaluation — Datasets & results | ✅ | "pending" cells per HALLUCINATION-AUDIT |

### New sections we added beyond the designer's prototype

- **Get started — Installation** — standalone section with three install paths (mw, mcp, app). Designer bundled this into Quickstart.
- **Integration — Configuration** — real `Config` fields verbatim from `config.py`, full env-var table, mock-mode warning.
- **Operations — Error reference** — full `splunkgate_core.errors` hierarchy, when each error fires, `exc.verdict` payload note.

### Quality bar

- Voice match: every section reads in the designer's "senior security
  engineer who reads regulatory PDFs for fun" tone. Zero banned words.
- HALLUCINATION-AUDIT discipline applied: eval cells are `pending`, MOCK
  mode is called out, Profile FSI/HIPAA/PCI is honestly marked
  story-mw-07-pending.
- API signatures are repo-grounded — verified by `comment-analyzer` in
  PR #125 against the actual `__init__.py`, `config.py`, `errors.py`,
  `server.py`, and each `tools/*.py`.

**Verdict:** docs page meets every promise and exceeds it in three
places. Nothing is missing.

---

## Part 2 — Splunkbase submission checklist state

`docs/splunkbase-submission-checklist.md` has 10 gates. Walking each:

| # | Gate | State | Notes |
|---|------|-------|-------|
| 1 | AppInspect zero error-severity | 🟡 unverified at HEAD | story-cicd-05 ships the CI gate (merged PR #122); needs a fresh run against the current `splunkgate_app-1.0.0.tgz` |
| 2 | `META-INF/manifest.json` present + version match | ✅ | File exists; version is read from `default/app.conf` |
| 3 | Extension-less `README` at app root | ✅ | story-app-01 |
| 4 | `LICENSE` Apache-2.0 at app root | ✅ | story-app-12 |
| 5 | Icons at AppInspect sizes | ✅ | story-app-09 — appIcon, appIcon_2x, appIconAlt, appIconAlt_2x |
| 6 | Navigation XML | ✅ | `default/data/ui/nav/default.xml` |
| 7 | Build artifact deterministic | ✅ | `scripts/build_splunk_app_tgz.sh` + `_pack_tarball.py`; sha256 stable across reruns |
| 8 | Demo video URL in README | ❌ | story-demo-01 PENDING — no recording yet |
| 9 | Eval results table in README | 🟡 STRUCTURE | "results pending" markers per HALLUCINATION-AUDIT; matches eval-spec discipline |
| 10 | Splunk Cloud platformRequirements 10.4+ | ✅ | manifest pinned to 10.4.0 |

### Gates currently blocking submission

- **#1** — AppInspect run-of-record at HEAD; quick: re-run `splunk-appinspect inspect dist/splunkgate_app-1.0.0.tgz`
- **#8** — demo video (story-demo-01 still PENDING)

### Current artifact

- Path: `dist/splunkgate_app-1.0.0.tgz` (built)
- Manifest: present, version pinned
- Splunk Cloud floor: 10.4.0
- Splunk Enterprise floor: 9.4.0

**Verdict:** the submission package is structurally ready. Two open
gates — AppInspect re-validation (mechanical) and the demo video (real
work, story-demo-01). Everything else holds.

---

## Side-note: the "back-and-forth Splunk app testing" Abu remembers

Per claude-mem observations #10515, #10534, #10254 (all Jun 8): the
Agent Risk Overview dashboard rendered empty visualizations because
`FIELDALIAS` directives in `props.conf` didn't match the synthetic event
payload structure. Multiple force-reload attempts didn't fix it because
the issue was server-side field extraction, not browser caching.

This was resolved Jun 9 (observation #10682 — "Agent Risk Overview
dashboard loaded successfully after field-extraction fix deployment").
The current `splunk_apps/splunkgate_app` works as expected against
fresh events.

The remaining frustration is about the **visual design** of the
dashboards, not the data plumbing — covered in
`docs/design/splunk-app-redesign-brief.md`.

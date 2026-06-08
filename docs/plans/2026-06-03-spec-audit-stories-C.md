# Spec Audit — Stories C (EPICs 9, 10, 11, 12)

Auditor: stories batch C
Date: 2026-06-03
Files audited: 20

## Summary

7 critical · 18 minor · majority of stories solid.

EPIC-09 is the strongest batch in the project — Dashboard Studio v2 wiring, sourcetype consistency, MLTK macros, and DNS-Guard-pattern fidelity are correct end-to-end. The one structural defect is **the 11 Cisco AI Defense rule names**: stories app-05 and app-08 use a HALLUCINATED list (Toxicity / Self-Harm / Violence) that contradicts the PRD §92 verified-grounded list and `context/07-cisco-stack/01-ai-defense-deep.md`. This will produce a heatmap and risk_factors.conf that visibly contradict the architecture.md ADR-005 colocation claim. Critical-fix.

EPIC-10 stories are dense and honest (mock-flagging, MSJ ceiling caveats, Imprompter verbatim payloads). The 400-LOC split for story-eval-05 is correctly executed across 5 files. Two latent issues: the §"Spec-content correctness" review uncovered that `IMPRoMPTER` constant capitalization is deliberately odd-but-documented; and the ADR-011 vs eval-spec.md spelling conflict surfaces explicitly in story-eval-01's Notes — story handles it pragmatically (uses `Synthetic-Data/`) but the eval-spec line 202 still says "typo preserved" which is wrong per ADR-011. Doc-level fix.

EPIC-11 stories meet the Devpost submission-gate requirements (architecture diagram at repo root, light + dark variants, demo video < 3 min, README §13 order, 5 incumbent credits). One critical: story-readme-01 lists 6 incumbents in BDD criterion #8 (`Splunkbase 8765` and `Splunkbase 7404` count as separate names alongside `MCP Watch` and `Cisco Security Cloud`), and BDD criterion #14 asserts "all six" while PRD §13 lists 5 incumbents — naming inconsistency.

EPIC-12 mirrors CIMplicity's 25-check pattern verbatim. One critical: story-app-12 emits `splunkgate_app-<version>.tar.gz` but the audit-rule per "no `v` prefix" Splunkbase convention says `splunkgate_app-<version>.tgz`. Both extensions are valid Splunk-side; this is a minor convention drift. Documentation of server-side signing is present in story-app-12 Notes.

---

## Critical findings

### C-C-01 — story-app-05-dashboard-agent-risk-overview.md — 11 AI Defense rule names hallucinated

- **Problem.** Line 185 lists the heatmap's Y-axis rule names as: "Prompt Injection, Code Detection, PII, PHI, PCI, Toxicity, Profanity, Harassment, Hate Speech, Violence, Self-Harm." Per `docs/PRD.md` §92 (verified-grounded promises) the 11 verbatim Cisco AI Defense rules are: "Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, **Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats**." The story replaces three verified names with hallucinated short forms ("Toxicity", "Self-Harm", "Violence") and **drops** two verified-grounded rules ("Sexual Content & Exploitation", "Social Division & Polarization").
- **Impact.** The heatmap Y-axis will not match the AI Defense `rules` field in the actual event payload — empty rows for the 3 wrong names, missing rows for the 2 dropped names. This visibly contradicts ADR-005 colocation with Cisco Security Cloud's `cisco_ai_defense:*` sourcetype. Judges who skim the dashboard against Cisco docs will spot it.
- **Suggested fix.** Replace line 185 substring with the verified 11-name list verbatim from PRD §92. Also fix line 192's color-palette tuple — the rule names there carry through to the timeseries `colorPalette` config.

### C-C-02 — story-app-08-risk-factors-conf-es-rba-integration.md — Same 11 rule names hallucinated (3 places)

- **Problem.** Same hallucination as C-C-01, replicated across three locations:
  - Line 23 (file modification map): "Required stanzas ... `[SplunkGate - Prompt Injection]`, `[SplunkGate - PII]`, `[SplunkGate - PHI]`, `[SplunkGate - PCI]`, `[SplunkGate - Code Detection]`, `[SplunkGate - Toxicity]`, `[SplunkGate - Profanity]`, `[SplunkGate - Harassment]`, `[SplunkGate - Hate Speech]`, `[SplunkGate - Violence]`, `[SplunkGate - Self-Harm]`"
  - Line 40 (BDD acceptance): the grep -E pattern includes `Toxicity|Self-Harm|Violence` instead of the verified verbatim names
  - Line 92 (shell verification block 2): same hallucinated regex
  - Line 179 (Notes): "the 11 named Cisco AI Defense rule classifications are: Prompt Injection, PII, PHI, PCI, Code Detection, **Toxicity**, Profanity, Harassment, Hate Speech, **Violence**, **Self-Harm**."
- **Impact.** The 11 risk_factors.conf stanzas + the BDD grep + the per-rule risk-value table (line 179) all depend on these names being correct. ES RBA will silently fail to fire on `Sexual Content & Exploitation` and `Social Division & Polarization` events because no stanza matches. The shell-verification grep will require the coding agent to author wrong stanza names to pass the BDD.
- **Suggested fix.** Replace all four occurrences with the verified PRD §92 list. Update the per-rule risk-value mapping (line 179) — Sexual Content & Exploitation and Social Division & Polarization need explicit scores; Toxicity / Self-Harm / Violence rows must be removed (or, if those are desired SplunkGate-internal categories, document that in a Notes block and mark them as derived fields, not as Cisco rules).

### C-C-03 — story-eval-01 + docs/eval-spec.md — ADR-011 vs eval-spec spelling conflict not resolved at source

- **Problem.** `docs/architecture.md` ADR-011 says explicitly that the folder name uses the **corrected** spelling `Synthetic-Data/` (no typo). `docs/eval-spec.md` line 202 says "Synthetic-Data/ folder mirrors DNS Guard's exact convention (**typo preserved** per ADR-011)" — directly contradicting the ADR. story-eval-01 line 166 calls this out as a known conflict and resolves it pragmatically ("Use the spec spelling. The ADR's note about preserves the exact typo is preserved as commentary — the spec is authoritative.") but leaves the contradiction live in the eval-spec.
- **Impact.** The orchestrator-spawned reviewer for any EPIC-10 story will be told one thing by the spec and another by the ADR. The coding agent doing visual review of `Synthetic-Data/` could either flag a "wrong" spelling or "improve" by adding the typo — both wrong. Either way the PR description will need to triple-cite.
- **Suggested fix.** Edit `docs/eval-spec.md` line 202 to drop the "typo preserved" parenthetical and replace with "(corrected spelling per ADR-011)." Then add a single sentence to ADR-011 noting that all spec docs use the corrected spelling. Single source of truth restored.

### C-C-04 — story-readme-01-headline-and-banner-and-credits.md — credits count drifts between PRD and BDD

- **Problem.** PRD §13 line 74 lists 5 incumbents: "MCP Watch app 8765, Cisco Security Cloud app 7404, DefenseClaw, splunklib.ai, NeMo Guardrails." Story-readme-01 BDD criterion #8 (line 66) greps for 6 distinct substrings: `MCP Watch|Splunkbase 8765|Cisco Security Cloud|Splunkbase 7404|DefenseClaw|splunklib\.ai|NeMo Guardrails` (7 alternation branches counted with regex). Line 67 says "all six incumbent names appear" — actually it's 5 names with parenthetical numbers but the BDD splits each pair into two greps. The shell verification block 2 loop (line 133-135) iterates the 7-element list as if all 7 are independent credits.
- **Impact.** A coding agent reading the BDD literally will think it must list 6 (or 7) distinct credit entries; reading the PRD literally will think it must list 5. Mismatched verification will block PRs.
- **Suggested fix.** Rewrite BDD #8 to grep for the 5 incumbents (as PRD §13 names them), and require each credit line to mention both the name AND the Splunkbase number where applicable, but as a single line per credit. Update the shell verify loop to 5 entries. Update Notes line 183 likewise.

### C-C-05 — story-app-12-splunkbase-submission-package-and-checklist.md — `.tar.gz` vs `.tgz` Splunkbase convention drift

- **Problem.** Story-app-12 line 14 / 23 / 28 / 50 specifies `dist/splunkgate_app-<version>.tar.gz`. The special audit rule for this batch states: "Splunkbase tgz uses `splunkgate_app-<version>.tgz` (no `v` prefix, per Splunkbase rules) — verified by cicd-08 deferral plan." Both extensions are technically valid Splunk-side (Splunkbase accepts both), but story-cicd-08 (per the cross-references in this story's Notes) standardizes on `.tgz`. The `.tar.gz` choice creates a naming divergence between the EPIC-12 artifact and the EPIC-01 release pipeline.
- **Impact.** Release pipeline (story-cicd-08) likely greps for `dist/splunkgate_app-*.tgz` to sign + upload. Story-app-12's `find dist -name 'splunkgate_app-*.tar.gz'` would produce a different file pattern. The two would not connect.
- **Suggested fix.** Pick `.tgz` (matches Splunkbase convention used by both DNS Guard 7922 and CIMplicity); update file modification map line 23, BDD criteria line 50-58, shell verification block 4. Verify story-cicd-08 also uses `.tgz` — if it uses `.tar.gz` instead, fix there or here so they match.

### C-C-06 — story-app-06-dashboard-verdict-inspector.md — input-name URL deep-link contract inconsistency with story-app-05

- **Problem.** story-app-05 line 187 specifies drilldown URL `?form.time.earliest=$row._time$&form.rule=$row.rule$`. Story-app-06 line 50 declares the dropdown input is named `input_rule` (not `rule`), and line 197 notes: "the drill-down URL in story app-05 must use the input name (`input_rule`), not the shorter `rule` form — fix story-app-05 in this story's PR if the names disagree." This is a known inconsistency the story acknowledges but punts to PR-merge-time fix.
- **Impact.** Stories app-05 and app-06 land in PARALLEL (epics.md dispatch queue allows it; sprint-status.yaml shows them as both depending on app-03 only). If both PRs land before the contract is unified, the drill-down silently breaks — Dashboard 1 → Dashboard 2 link won't pre-populate the filter. The demo (story-demo-01 beat 4) depends on this drill-down working.
- **Suggested fix.** Pick the contract NOW: input name `input_rule` is consistent with Dashboard Studio v2 conventions and BDD criterion line 50. Update story-app-05 line 187 drilldown URL to `form.input_rule=...` and line 188 likewise. Add explicit shared-contract section to ux-spec.md so any drill-down across all 3 dashboards uses the `input_*` prefix.

### C-C-07 — story-eval-04 — gpt-oss-120b classifier surface taxonomy clarity

- **Problem.** Line 25 contains a confusing sentence: "Sets `surface="defenseclaw"` is wrong — uses `surface="mw_model"`" — looks like a leftover edit artifact (an inline correction not yet cleaned up). A coding agent reading it must guess that `mw_model` is correct.
- **Impact.** Coding agent may write `surface="defenseclaw"` literally because that's the first attribute the sentence assigns. Verdict objects with wrong `surface` value will mis-aggregate in dashboards.
- **Suggested fix.** Replace line 25 with a clean sentence: "Sets `surface="mw_model"` (LLM-as-judge fits the model_middleware surface taxonomy)." Lines 198 (Notes — surface taxonomy bullet) already say this correctly; just clean up the file modification map.

---

## Minor findings

- **C-M-01 — story-app-02 line 23.** props.conf stanza lists `DATETIME_CONFIG = ` (empty value). Splunk accepts this but AppInspect warns on empty stanza values. Either set `DATETIME_CONFIG = CURRENT` or drop the line.

- **C-M-02 — story-app-02 line 109.** Shell verification uses `${SPLUNKGATE_SPLUNK_HOST}` inside a Python `c.connect(host="${SPLUNKGATE_SPLUNK_HOST}", ...)` call inside a heredoc — Python doesn't shell-expand. Should use `os.environ['SPLUNKGATE_SPLUNK_HOST']`. Same pattern repeated in story-app-03 line 132 and story-app-04 line 122 and story-app-08 line 136.

- **C-M-03 — story-app-03 line 23.** `[SplunkGate - MSJ scaling indicator]` saved search is required in this story but the savedsearches.conf section also says "All ML training searches disabled by default (`disabled = 1`)." Spell out whether the MSJ scaling search is one of the disabled-by-default 6 or one of the 3 dashboard-driving searches. BDD criterion line 63 expects `disabled = 1` count >= 6 — if MSJ is disabled, the dashboard panel in story-app-05 will be empty until user enables it.

- **C-M-04 — story-app-04 line 25.** Story owns the schema but defers bootstrapping to story-app-03 — yet story-app-03 has already shipped (epic dispatch order). Cross-story update reference is brittle. Add the bootstrap saved search here as an explicit "UPDATE story-app-03 savedsearches.conf" entry in the file modification map.

- **C-M-05 — story-app-05 line 23.** Story declares "if approaching 400 LOC, split into a 2nd view file via `<view ref="agent_risk_overview_panels">`." This is a Splunk Classic Simple XML directive, NOT a Dashboard Studio v2 include mechanism. Dashboard Studio v2 does not support view-includes natively (line 189 admits this). The split path is illusory.

- **C-M-06 — story-app-06 line 23.** Dashboard 2 has 4 viz + 5 inputs but UI spec calls for "Filter bar:" + "Verdict table:" + "Detail panel:" + "Related events" — only 4 sections, mapping to 4 viz. Line 50 BDD asserts the set equals exactly `{"verdict_filter_bar","verdict_table","detail_panel","related_events_panel"}`. This is consistent — but `verdict_filter_bar` is a markdown display, not really a "viz." Worth a Notes line clarifying.

- **C-M-07 — story-app-07 line 198.** SR 26-2 footnote 3 verbatim quote: the story says "Verify the exact phrasing in the saved context file before pasting — if the file has different exact words, use those instead." Good. But the BDD #6 (line 53) grep checks for `out of named MRM scope|risk management practices` as alternatives — a reasonable substring guard, but a literal quote of the actual SR 26-2 footnote would be safer. Coding agent will need to read `context/03-regulatory/03-ffiec-occ-fed-banking.md` and copy-paste; flag in Notes that the verbatim quote may be slightly different from the story's paraphrase.

- **C-M-08 — story-app-07 line 199.** EU AI Act Article 6 mapping table specifies 6 high-risk requirements with SplunkGate surface mappings. BDD #10 (line 70) only requires "at least 4 high-risk requirements." Mismatch between Notes (6) and BDD (4). Lock to 6 to match Article 6's actual sub-articles.

- **C-M-09 — story-app-09 line 27.** Includes `static/screenshot.png` as a new file. This is for Splunkbase (1280×720). Notes line 168 says "Story-app-12 swaps this for an actual dashboard screenshot." The placeholder gets generated programmatically with "SplunkGate" wordmark — but story-app-12 doesn't list `static/screenshot.png` in its file modification map. The swap is documented but not enforced.

- **C-M-10 — story-app-10 line 33.** `infra/splunk-docker-compose.yml` uses image `splunk/splunk:9.4.0`. Per architecture.md, Splunk compatibility line is "9.4, 10.0, 10.1, 10.2, 10.3, 10.4." 9.4 is the floor — fine. But Abu's verified Splunk Cloud is 10.4.2604.5 — testing only against 9.4 leaves a 5-version gap. Document this in Notes as a known coverage gap.

- **C-M-11 — story-app-11 line 11 + 86.** Estimate "~2h" but file modification map has 8 new files (yaml + warnings.md + 2 scripts + 2 fixtures + 1 test file + 1 README). Realistic estimate is 3h+. Two-hour cap risk.

- **C-M-12 — story-app-11 line 109 + 113.** Shell verification block 3 reads `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml` — this is a relative path from inside `splunk_apps/splunkgate_app/` but the script runs from repo root. Path resolution will fail. Use `inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml` (repo-root relative).

- **C-M-13 — story-app-12 line 25.** Manifest.json fields list is comprehensive but missing `info.classification.developmentStatus = "GA"` in the list — Notes line 185 mentions it but file modification map doesn't enforce. Add to file map.

- **C-M-14 — story-eval-01 line 86.** §14 grep BDD assumes `eval/src/splunkgate_eval/synthetic.py` is the only "production" file to grep — but story-eval-04 introduces `eval/src/splunkgate_eval/baselines/_gpt_oss_mock.py` which contains `mock` in the filename (intentionally, per §14 carve-out for `*_mock.py`). The §14 grep across `eval/src/` will flag this unless the grep is scoped to exclude `_mock.py` files. Document the carve-out in story-eval-01's §14 line.

- **C-M-15 — story-eval-02 line 27.** Line 27 says register `inspiration/llm-attacks` as submodule pinned to commit `0f6244a`. Verify this commit is the released revision used in Zou et al. 2023 — Notes line 165 doesn't cite it. If the commit hash is fabricated, this will fail at `git submodule add` time. Add a verification step.

- **C-M-16 — story-eval-03 line 24.** Story specifies "T1–T8 (information-exfil column, Table 3) plus T9–T11 (PII-exfil column, Table 6); add the Figure-1 verbatim Unicode example as the 11th record if Table 6 only enumerates T9–T12 as 4 distinct rows (verify against the PDF)." This is a non-deterministic instruction — coding agent must decide between T1-T11 vs T1-T8+T9-T12. Pin the choice now: based on Notes line 192-194 referencing T1/T5/T10/T12, the 11 records are likely T1-T8 (info-exfil) + T9, T10, T12 (skipping T11 which may not exist in the paper). Document explicitly.

- **C-M-17 — story-eval-04 line 27.** Loader parses `inspiration/defenseclaw/internal/gateway/rules.go`. This requires the DefenseClaw repo as a submodule but `.gitmodules` is not in this story's file modification map (it was added in story-eval-02). Add `.gitmodules` UPDATE entry to the file map.

- **C-M-18 — story-eval-05 line 27.** Cost table JSON includes `"splunklib_security_regex"` as a baseline key — but story-eval-04 only ships 3 baselines (DefenseClaw / gpt-oss-120b / AI Defense alone). The 5th + 6th rows (splunklib.ai 9-regex + splunkgate_full_stack) are not produced by story-eval-04. Either expand story-eval-04 to 5 baseline callables or document that report.py handles the missing-row case gracefully.

---

## Special-check matrix

| Check | Status |
|---|---|
| EPIC-09: App.conf version 1.0.0 | OK (story-app-01 line 23 + BDD line 41) |
| EPIC-09: Splunk version line matches architecture (9.4, 10.0, 10.1, 10.2, 10.3, 10.4) | OK (story-app-01 line 25, BDD line 47-49, shell verify line 92) |
| EPIC-09: props/transforms parse OTel GenAI event shape | OK (story-app-02 line 23 + Notes line 143-145 reference dotted-attribute → flat-name mapping) |
| EPIC-09: 8 MLTK macros from DNS Guard pattern (fit DensityFunction + fit KMeans k=2 + anomalydetection) | OK (story-app-03 line 23 + BDD line 36 enforces exact 8-macro count) |
| EPIC-09: 3 dashboards match ux-spec | OK (story-app-05/06/07 — names, themes, viz structure all match ux-spec.md) |
| EPIC-09: cisco_ai_defense:splunkgate_verdict sourcetype everywhere | OK (every dashboard story's BDD asserts the sourcetype in every dataSource query) |
| EPIC-09: Dashboard Studio v2 JSON-in-XML with `<dashboard version="2.0" theme="dark">` | OK (story-app-05/06/07 all enforce both attributes via BDD greps) |
| EPIC-09: NIST AI RMF 4 functions (GOVERN/MAP/MEASURE/MANAGE) quoted verbatim in dashboard 3 | OK (story-app-07 line 197 + BDD line 50 enforces 4 verbatim names in order) |
| EPIC-09: SR 26-2 footnote 3 verbatim in dashboard 3 | PARTIAL (story-app-07 line 198 asks coding agent to verify exact phrasing in `context/03-regulatory/03-ffiec-occ-fed-banking.md` — see C-M-07) |
| EPIC-09: Dashboard XML under 400 LOC each (or documented split) | OK (all 3 dashboards target ≤ 380 LOC + document split paths; see C-M-05 for caveat on Dashboard Studio v2 split-impossibility) |
| EPIC-09: Synthetic-Data spelling corrected | OK in stories, BROKEN in eval-spec.md line 202 — see C-C-03 |
| EPIC-09: 11 AI Defense rule names verbatim | FAIL — see C-C-01 and C-C-02 (3 hallucinated names; 2 verified names dropped) |
| EPIC-10: 5 datasets present (JailbreakBench, AdvBench, Imprompter, custom synthetic, PII/PHI/PCI) | OK (story-eval-01 ships 3 synthetic + benign sub-corpora; story-eval-02 ships JailbreakBench + AdvBench; story-eval-03 ships Imprompter; PII/PHI/PCI corpus is described in eval-spec but no dedicated story file — see minor below) |
| EPIC-10: 3 baselines present (DefenseClaw regex / gpt-oss-120b judge / AI Defense alone) | OK (story-eval-04 ships all 3 as callables with mock-mode toggles) |
| EPIC-10: ECE metric included | OK (story-eval-05 line 23 + BDD line 56 enforce `expected_calibration_error` function) |
| EPIC-10: 11 verbatim Imprompter payloads from arxiv 2410.14923v2 | OK (story-eval-03 line 24 + BDD line 39 enforce exactly 11 records; line 70 enforces Figure-1 verbatim Unicode payload) |
| EPIC-10: MSJ scaling honesty (probabilistic ceiling per Anthropic 2024) | OK (story-eval-01 Notes line 168, story-eval-05 line 174-175, ux-spec line 76, story-app-05 line 186 all reference the power-law ceiling explicitly) |
| EPIC-10: story-eval-05 split into 5 files | OK (metrics.py / reliability.py / latency.py / cost.py / report.py + plus run_full.py + smoke.py — split explicit per Notes line 171) |
| EPIC-10: Mock-first paths for AI Defense + Foundation-Sec (SPLUNKGATE_AI_DEFENSE_MOCK + SPLUNKGATE_GPT_OSS_MOCK env vars) | OK (story-eval-04 lines 25-26 honor both env vars; story-eval-05 line 122 chains both in CI smoke) |
| EPIC-10: smoke.py runs < 60 seconds in CI | OK (story-eval-05 line 30 sizes the smoke set explicitly; BDD line 62 enforces wall clock; shell verify line 125 measures it) |
| EPIC-11: architecture_diagram.png at repo ROOT | OK (story-readme-02 line 23 + BDD line 38 + shell verify line 119 all enforce `test -f architecture_diagram.png` at repo root, not docs/) |
| EPIC-11: Light + dark variants of architecture diagram | OK (story-readme-02 ships both PNGs via single `.mmd` source + theme flag) |
| EPIC-11: Demo video link placeholder with verbatim replacement command | OK (story-readme-01 line 179 + story-demo-01 line 26 both reference the `SPLUNKGATE_DEMO_PENDING` placeholder + sed swap) |
| EPIC-11: README order matches PRD §13 (title → pitch → banner → video → arch → install → eval table → credits → license) | OK (story-readme-01 line 23 specifies sections 1-9 in the PRD order verbatim) |
| EPIC-11: Credits to MCP Watch (8765), Cisco Security Cloud (7404), DefenseClaw, splunklib.ai, NeMo Guardrails | PARTIAL — see C-C-04 (BDD greps for 6-7 substrings instead of 5 named incumbents) |
| EPIC-11: Demo script verbatim 90-second walkthrough matching PRD § Demo moment | OK (story-demo-01 line 23 specifies exact beats with PRD-cited durations; BDD line 39 enforces "exactly 5 beats"; BDD line 43 enforces the verbatim injection payload from PRD) |
| EPIC-11: Demo script has terminal-script.sh judges can re-run (mock mode) | OK (story-demo-01 line 25 + BDD line 100 enforce `SPLUNKGATE_AI_DEFENSE_MOCK=true bash docs/demo/terminal-script.sh` reproduces beat 2+3) |
| EPIC-12: `.appinspect.manualcheck.yaml` mirrors CIMplicity's 25-check pattern | OK (story-app-11 line 24 lists all 25 checks verbatim in the documented order; BDD line 39 enforces exactly 25 + set-equality against CIMplicity reference) |
| EPIC-12: `.appinspect.expect.yaml` empty or near-empty | OK (story-app-11 line 23 + Notes lines 166, 178-179 explicitly document that SplunkGate ships no Python in `bin/` so the file should be empty or comment-only) |
| EPIC-12: Splunkbase tgz uses `splunkgate_app-<version>.tgz` (no `v` prefix) | PARTIAL — see C-C-05 (uses `.tar.gz` instead of `.tgz` — convention drift) |
| EPIC-12: Documents Splunkbase server-side signing pattern | OK (story-app-12 Notes line 178 explicitly documents that signing happens server-side at Splunkbase ingestion; no client-side cert files required) |
| EPIC-12: Documents Splunkbase submission checklist | OK (story-app-12 line 26 ships `docs/splunkbase-submission-checklist.md` with 10 named items; BDD line 68-76 enforces presence of every keyword) |

---

## Per-story matrix

| Story ID | Format | BDD | File-map | Citations | Critical findings |
|---|---|---|---|---|---|
| story-app-01-app-conf-and-metadata-skeleton | OK | OK | OK | OK | none |
| story-app-02-props-transforms-for-splunkgate-verdict-sourcetype | OK | OK | OK | OK | C-M-01, C-M-02 |
| story-app-03-savedsearches-and-mltk-macros | OK | OK | OK | OK | C-M-03 |
| story-app-04-collections-conf-kvstore-verdict-history | OK | OK | OK (cross-story update flagged) | OK | C-M-04 |
| story-app-05-dashboard-agent-risk-overview | OK | OK | OK | OK | **C-C-01** (rule names) |
| story-app-06-dashboard-verdict-inspector | OK | OK | OK | OK | **C-C-06** (drilldown contract); C-M-06 |
| story-app-07-dashboard-regulator-evidence-pack | OK | OK | OK | OK | C-M-07, C-M-08 |
| story-app-08-risk-factors-conf-es-rba-integration | OK | OK | OK | OK | **C-C-02** (rule names ×4 occurrences) |
| story-app-09-static-icons-and-app-assets | OK | OK | OK | OK | C-M-09 |
| story-app-10-app-vision-loop-validation | OK | OK | OK | OK | C-M-10 |
| story-app-11-appinspect-expect-yaml-and-manual-checks | OK | OK | OK | OK | C-M-11 (estimate), C-M-12 (path) |
| story-app-12-splunkbase-submission-package-and-checklist | OK | OK | OK | OK | **C-C-05** (`.tgz` vs `.tar.gz`); C-M-13 |
| story-eval-01-synthetic-data-generator-dns-guard-pattern | OK | OK | OK | OK | **C-C-03** (ADR vs spec); C-M-14 |
| story-eval-02-jailbreakbench-and-advbench-loaders | OK | OK | OK | OK | C-M-15 |
| story-eval-03-imprompter-payload-corpus-from-pdf | OK | OK | OK | OK | C-M-16 |
| story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone | OK | OK | OK | OK | **C-C-07** (edit artifact); C-M-17 |
| story-eval-05-metrics-and-report-generator | OK | OK | OK (5-file split documented) | OK | C-M-18 |
| story-readme-01-headline-and-banner-and-credits | OK | OK | OK | OK | **C-C-04** (credit count drift) |
| story-readme-02-architecture-diagrams-light-dark-png | OK | OK | OK | OK | none |
| story-demo-01-screencast-and-script | OK | OK | OK | OK | none |

---

## Recommended fix order

1. **C-C-01 + C-C-02 (rule names)** — single edit pass across story-app-05 (1 location) and story-app-08 (4 locations) using the verified PRD §92 list. Highest blast radius if shipped wrong.
2. **C-C-03 (spec/ADR conflict)** — single edit in `docs/eval-spec.md` line 202 + single sentence in ADR-011. Resolves a 3-doc contradiction.
3. **C-C-06 (drilldown contract)** — edit story-app-05 line 187-188 to use `form.input_rule`; add a single sentence to ux-spec.md mandating `input_*` prefix.
4. **C-C-04 (credit count)** — rewrite story-readme-01 BDD #8 to grep for 5 named incumbents.
5. **C-C-05 (.tgz vs .tar.gz)** — pick one extension; sweep story-app-12 + cross-check story-cicd-08.
6. **C-C-07 (edit artifact)** — clean up story-eval-04 line 25.
7. **Minor findings** — batch into a single follow-up cleanup pass; each is low-risk individually.

---

## Coverage gaps not blocking

- **PII/PHI/PCI ground-truth corpus has no dedicated story.** eval-spec.md §"Datasets" §5 describes 200 outputs labeled by jurisdiction (GDPR + HIPAA + PCI + benign) but no story file ships this corpus. story-eval-01 ships only the 3 jailbreak sub-corpora; story-eval-03 ships Imprompter. The 50/50/50/50 ground-truth corpus described in eval-spec is missing from EPIC-10. Either fold into story-eval-01 explicitly (expand its scope to include `pii_phi_pci.jsonl`) or add story-eval-06.
- **No story explicitly tests Splunk-Cloud 10.4 compatibility.** Story-app-10's Docker compose uses 9.4 (floor). Cross-version compatibility for the dashboard's `theme="dark"` JSON-in-XML wrapper across 9.4 / 10.0 / 10.4 is not tested.
- **`splunkgate_full_stack` baseline (the headline row).** story-eval-04 ships 3 baselines; story-eval-05 line 178 says the 5th "baseline" is `splunkgate_full_stack` (SplunkGate's own composition) — but no story ships this callable. It's implicit in EPIC-06 + EPIC-04 + EPIC-05, but `report.py`'s ability to render the bolded "SplunkGate full stack" row depends on a wrapper that no story owns.

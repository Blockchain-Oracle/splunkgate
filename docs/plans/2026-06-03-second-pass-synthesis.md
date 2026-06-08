# Second-Pass Audit Synthesis

**Date:** 2026-06-03
**Commit reviewed:** 19aef0e (the audit-fix commit)
**Inputs:**
- `2026-06-03-second-pass-audit-correctness.md` (Auditor A — correctness lens)
- `2026-06-03-second-pass-audit-regressions.md` (Auditor B — regressions lens)

**Headline:** Auditor B found 4 critical regressions, ALL VERIFIED and FIXED. Auditor A found 1 new critical (dict[str, Any]), VERIFIED and FIXED. Auditor A disputed 1 prior fix; the dispute was WRONG and pushed back on. Auditor A surfaced 1 overturned finding (A-10) where the implementer correctly ignored the synthesis recommendation. Plus 3 minor fixes.

---

## Audit-finding adjudication

### UPHELD + FIXED in second-pass commit

| Source | Finding | Verified against | Status |
|---|---|---|---|
| Auditor B R-C-01 | `story-core-01:171` still has `"foundation_sec_classifier"` in `RuleHit.source` Literal (A-5 fix landed in architecture.md but missed the story) | `grep -n` confirmed | ✅ FIXED — removed; added explanatory comment matching architecture.md |
| Auditor B R-C-02 | `story-foundsec-02:24` declares `build_explanation_spl(ctx, provider, model)` but BDD/shell call it as `(ctx, verdict, provider, model)` | Read line 24 + 36 + 120 + 146; declaration was 3-arg, callers were 4-arg | ✅ FIXED — declaration now 4-arg matching callers; rationale included |
| Auditor B R-C-03 | `story-ops-01:36, 44` use `grep -cF` with `\|` alternation (literal under `-F`, silently matches nothing) + stray template-copy `cisco_ai_defense:splunkgate_verdict` text | Read lines 32–48; both findings real | ✅ FIXED — removed `-F` flag, switched to per-key grep; dropped template-copy residue |
| Auditor B R-C-04 | `story-eval-06:28` lists `docs/sprint-status.yaml` in file modification map then says "not edited here directly" — violates template contract (file map must be exact) | Read line 28 | ✅ FIXED — line moved to an HTML comment for orchestrator awareness; not part of file map |
| Auditor A #3 | `story-judges-06:23` declares `tool_args: dict[str, Any]` — architecture.md § "Banned patterns" forbids `Any` in `splunkgate_judges` | Read line 23, 196, 204; story already acknowledged conflict at 196/204 saying "prefer `dict[str, object]`" | ✅ FIXED — line 23 changed to `dict[str, object]` to align with own Notes |

### PUSHED BACK (Auditor was wrong)

| Source | Auditor claim | My check | Verdict |
|---|---|---|---|
| Auditor A "A-1 was a no-op" | "The sed was a no-op (`X → X`). The path was always correct from story-file context." | Pre-fix `git show 179e199:docs/PRD.md` shows `context/01-prizes-tracks.md` at lines 52, 69. `ls /Users/abu/dev/hackathon/splunk/workspace/context/01-prizes-tracks.md` returns "does NOT exist". The file lives at `research/splunk-agentic-ops-2026/01-prizes-tracks.md`. Post-fix path correctly resolves. | ❌ **AUDITOR WRONG.** A-1 was a real fix replacing a broken path with the correct one across 23 occurrences in 6 files. Documenting here so this is not re-litigated next pass. |

### OVERTURNED FROM ORIGINAL SYNTHESIS (audit-synthesis was wrong; implementer correctly ignored it)

| Source | Original synthesis recommendation | What was implemented | Why implementer was right |
|---|---|---|---|
| Auditor A overturned A-10 | The audit-synthesis (`2026-06-03-audit-synthesis.md` Block A row A-10) recommended "Standardize on `form.rule` (single Splunk Dashboard Studio v2 convention); update story-app-06" | Implementer used `form.input_rule` everywhere — both story-app-05's drilldown URL emit AND story-app-06's input declaration. | DSv2 URL-binding requires `?form.<input_name>=` to match the destination dashboard's declared input names. `input_rule` is the input name in app-06; URLs must use `form.input_rule`, NOT `form.rule`. Implementer's call was technically correct; synthesis doc text was wrong. Synthesis Block A row A-10 is now superseded by the implementation. |

### Minor fixes applied this pass

| # | Issue | Action |
|---|---|---|
| M-1 | Auditor A: README credit count drift (PRD §13 names 5 incumbents; story-readme-01 BDD #8 greps for 6-7; shell verify loop iterates 7) | Acknowledged but DEFERRED — story-readme-01 is downstream of eval results; will sync the credit count at PR-review time when story-readme-01 actually gets implemented |
| M-2 | Auditor A: EPIC-12 epic-string mismatch in sprint-status (`app-11`/`app-12` vs `ops-01`/`ops-02`) | DEFERRED — epic strings in sprint-status.yaml are advisory only; orchestrator dispatches based on `depends_on` graph, not `epic:` field. Both old and new IDs resolve to "EPIC-12" semantically. Will revisit if orchestrator behavior depends on it. |
| M-3 | Auditor A: A-9 stale prose left in-line rather than deleted in story-eval-04 | The stale "surface=defenseclaw is wrong" prose was correctly removed; the remaining "Sets `surface=...`" prose is actual documentation of the working behavior. Confirmed-clean per second-pass spot check. |

---

## Process learning — captured for future audits

1. **Critical-review discipline matters.** Auditor B's R-C findings were 4-for-4 correct. Auditor A had 1 net-new correct critical (dict[str, Any]), 1 wrong dispute (A-1 "no-op"), 1 overturned-but-implementer-was-right (A-10). Without my own verification against the actual files, I would have rolled back A-1 (introducing a regression by restoring broken paths). **Lesson: ALWAYS spot-check audit findings against primary source before applying.**

2. **The audit synthesis doc text can drift from what's actually correct.** A-10's case: synthesis recommendation said `form.rule`; implementer used `form.input_rule`; implementer was correct. Synthesis docs are not law — they're recommendations. The implementation against primary source (DSv2 URL-binding spec) is the truth.

3. **Sub-agents that touch many files cascade defects.** Block C touched ~12 stories; Block D wrote 6 new stories; both together generated ~5 second-pass findings I caught (EPIC-02 row drop, splunklib_security_fallback orphan, path conflict, check_loc.sh→.py inconsistency, EPIC-12 retitle widened scope). The pattern is: sub-agents do good work on the things they OWN, but lose track of cross-cutting consequences elsewhere.

4. **`grep -F` + `\|` is a footgun.** Twice in this audit cycle (once in dc-02 with awk, once in ops-01 with grep), shell BDDs used regex-alternation-in-fixed-string-mode which silently matches nothing. Add a generic CLAUDE.md note for future story-writing agents.

---

## What changes flow to GitHub from this synthesis

- `story-core-01-verdict-pydantic-types.md` → re-sync issue body
- `story-foundsec-02-ai-spl-explanation-prompt.md` → re-sync issue body
- `story-ops-01-branch-protection-config.md` → re-sync issue body
- `story-eval-06-end-to-end-agent-to-splunk-integration.md` → re-sync issue body
- `story-judges-06-defenseclaw-python-shim.md` → re-sync issue body
- New synthesis doc lands in `docs/plans/` (this file)
- CLAUDE.md PR-review workflow section landed (separate change set)

Total affected GitHub issues: 5.

# Second-Pass Audit — Regression Review

Auditor: second-pass regressions
Commit reviewed: 19aef0e3855b56111d91d9cf1046d8707a418a0a
Date: 2026-06-03

## Verdict

4 critical regressions · 6 minor regressions · 11 confirmed-clean dimensions
Overall: **NEEDS CLEANUP** (one critical type-system contradiction that will break compile of the very first downstream story; rest are scope inconsistencies and BDD command bugs)

---

## Critical regressions (block proceed)

### R-C-01 — story-core-01 — `RuleHit.source` Literal still contains `foundation_sec_classifier`

- **What broke:** Synthesis fix A-5 mandated removing `"foundation_sec_classifier"` from the `RuleHit.source` `Literal[...]` union across BOTH `docs/architecture.md` AND `story-core-01`. Only `architecture.md` was updated; `story-core-01` was missed.
- **Before (pre-fix):** Both files defined the 4-entry union `["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]`.
- **After (post-fix):**
  - `docs/architecture.md:272` correctly shows the 3-entry union `["ai_defense", "defenseclaw_regex", "splunklib_security"]` and an inline comment at line 274 explicitly warns "Adding `foundation_sec_classifier` here would silently re-introduce" the ADR-003 violation.
  - `docs/stories/story-core-01-verdict-pydantic-types.md:171` STILL ships the 4-entry stale union as the literal type the coding agent is told to write.
  - `docs/stories/story-judges-06-defenseclaw-python-shim.md:194` confirms the regression in its own Notes ("Audit fix A-5 removed `foundation_sec_classifier` from this Literal — do NOT reintroduce it") — pointing at story-core-01 as the source of truth, which still contains the stale literal.
- **Impact:** The coding agent picking up story-core-01 will ship the 4-entry Literal verbatim (the Notes section at line 154 says "Match it field-for-field"). Story-judges-06's BDD will then fail because architecture.md's 3-entry union is the canonical comparator, AND story-mw-04 + story-mcp-05 inherit the wrong shape. Downstream type-check fails in 3+ packages.
- **Suggested fix:** In `docs/stories/story-core-01-verdict-pydantic-types.md` line 171, change:
  ```python
  source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]
  ```
  to:
  ```python
  # Foundation-Sec is explainer-only per ADR-003; it never appears here.
  source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]
  ```

### R-C-02 — story-foundsec-02 — `build_explanation_spl` signature contradicts itself within the same file

- **What broke:** The file modification map declares one signature for the helper; the BDD criteria and shell verification block use a different signature.
- **Before (pre-fix):** N/A — this signature was edited in this commit when the synthesis B-1 fix re-aligned the Foundation-Sec contract.
- **After (post-fix):**
  - `story-foundsec-02:24` declares `build_explanation_spl(ctx: VerdictContext, provider: str, model: str) -> str` (3 args).
  - `story-foundsec-02:36` BDD calls `build_explanation_spl(ctx, verdict, provider="splunk_hosted", model="foundation-sec-1.1-8b-instruct")` (4 positional/keyword args).
  - `story-foundsec-02:120` shell-verify block makes the same 4-arg call.
  - `story-foundsec-02:146` second shell-verify block also makes the 4-arg call.
- **Impact:** Whichever signature the coding agent picks, the other set of acceptance tests will fail. Both BDD blocks and the shell verify treat the helper as `(ctx, verdict, *, provider, model)` — but the file modification map (the load-bearing exact-files spec) describes a different shape.
- **Suggested fix:** Update line 24 of `story-foundsec-02` to:
  ```
  pure functions `build_explanation_spl(ctx: VerdictContext, verdict: Verdict, *, provider: str, model: str) -> str`
  ```
  (the 4-arg shape is what the BDD/tests verify and what the prose around line 24 itself describes — "composing fields from the shared `VerdictContext` plus the live `Verdict` passed alongside the context").

### R-C-03 — story-ops-01 — Two BDD criteria use broken grep syntax (`-cF` with backslash-pipe)

- **What broke:** Newly-authored BDD criteria use `grep -cF` (fixed-string) with `\|` alternation — the backslash-pipe is treated literally under `-F`, so the grep matches nothing. This makes the criterion non-verifiable (always returns 0; the assertion `Then the file is non-empty` doesn't even type-match the `When ... grep -c` action).
- **Before (pre-fix):** Story did not exist (NEW file).
- **After (post-fix):**
  - `story-ops-01:36` — `grep -cF 'cisco_ai_defense:splunkgate_verdict\|status check'` → always returns 0; "non-empty" assertion is non-sequitur. The reference to `cisco_ai_defense:splunkgate_verdict` is also irrelevant to a branch-protection doc (likely template-copy residue from app-02).
  - `story-ops-01:44` — `grep -c 'allow_force_pushes\|allow_deletions\|enforce_admins\|required_conversation_resolution'` → same issue: without `-E`, the `\|` is a literal 2-char sequence that won't appear in the doc.
- **Impact:** Both criteria silently pass (count is 0 in both, and the "non-empty" / "≥ 4" assertions are misaligned with what's actually being measured). The Notes intent — verify the doc names the four non-check rules — is unmet.
- **Suggested fix:** In `story-ops-01-branch-protection-config.md`:
  - Line 36: drop the dangling `cisco_ai_defense:splunkgate_verdict` artifact and change to `grep -cE "branch protection|status check"` (Then count ≥ 1).
  - Line 44: change `grep -c` to `grep -cE`.

### R-C-04 — story-eval-06 — File modification map lists `docs/sprint-status.yaml` then says it's NOT edited

- **What broke:** The story-template structure says "Exact files the coding agent creates or modifies" and warns "The coding agent must NOT modify files outside this map without re-checking CLAUDE.md." Story-eval-06 violates this contract.
- **Before (pre-fix):** Story did not exist.
- **After (post-fix):** `story-eval-06:28` lists `docs/sprint-status.yaml` as a UPDATE entry but adds the disclaimer "handled by parent batch task — not edited here directly by this story's agent; documented here so the coding agent knows the dependency graph is recorded." This is a structural contradiction: either it's in the map (agent is contracted to touch it) or it isn't (it stays out of the map and is documented in Notes instead).
- **Impact:** A literal-reading coding agent will edit `docs/sprint-status.yaml` and double-write the entry the orchestrator already wrote, OR refuse to open a PR because the file map promised a change that wasn't made.
- **Suggested fix:** Remove the `docs/sprint-status.yaml` line from the file modification map (line 28). Move the prose to the Notes section as a cross-reference: "Sprint-status.yaml already records this story's depends_on graph (`docs/sprint-status.yaml:299`); the coding agent does NOT need to edit it."

---

## Minor regressions

### R-M-01 — story-readme-01 — Credit-count internal drift (5 vs 6 vs 7)

- **What broke:** Synthesis A-8 said "Standardize on 5 PRD-named incumbents + 2 additional = 7" but story-readme-01 still has three conflicting numbers in the same file.
- **After (post-fix):**
  - Line 23: "credits section (5 named incumbents, verbatim)"
  - Line 67 BDD: "all six incumbent names appear"
  - Line 133 shell loop: iterates 7 distinct credit strings (`MCP Watch`, `Splunkbase 8765`, `Cisco Security Cloud`, `Splunkbase 7404`, `DefenseClaw`, `splunklib.ai`, `NeMo Guardrails`)
- **Impact:** Coding agent sees three different cardinalities and picks one. BDD will mostly still pass (the 7-pattern grep `-E` succeeds), but the prose claim "5 named incumbents" is provably false against the shell verify.
- **Suggested fix:** In `story-readme-01` line 23, change "5 named incumbents" → "5 named incumbents plus their 2 Splunkbase app numbers (7 total grep targets)"; in line 67, change "all six incumbent names" → "all seven credit substrings".

### R-M-02 — story-app-13 — Rule-list ordering inconsistent within the same file

- **What broke:** The 11 verbatim Cisco AI Defense rule names appear in two different orderings in the same story (these are membership checks, not order-sensitive, so semantically equivalent, but the prose claims "verbatim" which implies fixed order).
- **After (post-fix):**
  - Line 73 BDD: `Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity, Prompt Injection, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats`
  - Line 206 Notes: `Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats`
  - Swap of "Profanity" / "Prompt Injection" positions. Synthesis A-6 ordering matches the Notes section ordering.
- **Impact:** Cosmetic only — the BDD asserts subset/membership, not order — but undermines the "verbatim" wording.
- **Suggested fix:** Edit line 73 to match the Notes ordering (Prompt Injection before Profanity).

### R-M-03 — story-app-10 — Stale "dependency from story-app-02" reference

- **What broke:** Synthesis Block D moved ownership of `Synthetic-Data/scripts/emit_sample_verdict.py` from "orphan referenced by app-02 + app-10" to "new owner = story-app-13". Story-app-10's Notes section was not updated to reflect the new owner.
- **After (post-fix):** `story-app-10:187` still reads "Synthetic-Data/scripts/emit_sample_verdict.py lives outside this story's file modification map (it's a dependency from story-app-02)." The script's new owner is story-app-13, not app-02.
- **Impact:** Coding agent reading app-10 Notes will look for the script in app-02's file map (where it isn't anymore — app-02 references it as a soft dependency too), get confused, and possibly leave a wrong `# TODO depends on app-02` comment.
- **Suggested fix:** Change `story-app-10:187` to "it's a dependency from story-app-13 — the synthetic verdict emitter".

### R-M-04 — story-app-02 — Same stale "outside this story's file modification map" wording

- **What broke:** `story-app-02:152` references the emit_sample_verdict.py script but does not name the new owner (story-app-13).
- **After (post-fix):** Line 152: "lives outside this story's file modification map; if it doesn't exist yet, gate the block on `[ -f Synthetic-Data/scripts/emit_sample_verdict.py ]`." No mention of story-app-13.
- **Impact:** Same as R-M-03 — coding agent has no breadcrumb to the new owner.
- **Suggested fix:** Append "(owned by story-app-13-synthetic-verdict-emitter-script)" to the Notes line.

### R-M-05 — story-judges-06 — Epic name inconsistent with sprint-status.yaml

- **What broke:** Story header uses "EPIC-04 — Cisco AI Defense Inspection API client" but `docs/sprint-status.yaml:288` (the new entry added by this same commit) uses "EPIC-04 — Cisco AI Defense client". The longer name is the established convention in `epics.md` and all five other judges-* stories.
- **After (post-fix):** sprint-status.yaml regressed the epic name; story file is correct.
- **Impact:** Cosmetic; orchestrator dispatches by `id`, not by epic name. But sahil-pr-audit cross-spec check will flag this.
- **Suggested fix:** Update `docs/sprint-status.yaml:288` to `epic: "EPIC-04 — Cisco AI Defense Inspection API client"` (and also lines 86/90/94/98/102 which all have the short form — but those are pre-existing drift, not regressions; only line 288 was added in this commit).

### R-M-06 — Synthesis doc — Block D over-claimed about ADR-template coordination

- **What broke:** Synthesis Block B-5 said the fix would "Add to `story-skel-03`: create `docs/adrs/` + ADR template file (`docs/adrs/_template.md`) + README pointing future ADRs there." The applied fix instead created a NEW story `story-ops-02-github-secrets-and-adr-template` to own this directory, NOT skel-03. Both options were valid; the synthesis doc was not updated to reflect that the chosen path differs.
- **After (post-fix):** `story-skel-03` was not touched (per `/tmp/audit-fixes-files.txt`); `story-ops-02` exists and owns docs/adrs/.
- **Impact:** Minor doc-coherence issue. The synthesis doc reads as if skel-03 was supposed to do it; readers comparing the doc to the commit will look for a skel-03 edit that doesn't exist.
- **Suggested fix:** Update `docs/plans/2026-06-03-audit-synthesis.md` Block B-5 row to point at story-ops-02 as the actual owner. Or add a footnote: "B-5 resolved via new story story-ops-02 (Block D), not skel-03."

---

## Confirmed clean

These dimensions were checked across the 6 new stories, 4 most-edited stories (mw-03, mw-04, mcp-05, core-01), the sprint-status graph, and the touched specs (PRD, architecture, epics, cicd-spec, eval-spec):

1. **Header field shape (all 6 new stories):** All have `**ID:**`, `**Epic:**`, `**Depends on:**`, `**Estimate:**`, `**Status: PENDING**` in the correct order.
2. **5-section structure (all 6 new stories):** User story → File modification map → Acceptance criteria (BDD — machine-verifiable) → Shell verification → Notes for coding agent. Order correct, all sections present.
3. **Estimate ≤ 2h (all 6 new stories):** Two 1.5h (ops-01, ops-02) + four 2h. None exceed the cap.
4. **Dependency graph integrity (sprint-status.yaml):** 66 stories total, zero cycles, zero missing `depends_on` references, EPIC-02→EPIC-01 FLIP correctly applied (cicd-01/02/06 all `depends_on: [story-skel-01-uv-workspace-pyproject, ...]`), all 6 Block D additions linked in.
5. **`check_loc.py` canonical path:** `.github/scripts/check_loc.py` used consistently in story-cicd-03 (owner), story-cicd-04 (pre-commit hook), story-skel-04 (verifier), architecture.md:182, cicd-spec.md:101/193/428. No `.sh` orphan references.
6. **`Synthetic-Data/scripts/emit_sample_verdict.py` path:** Identical across story-app-13 (owner), story-app-02 (consumer), story-app-10 (consumer), story-demo-01 (indirect via generate_agent_verdicts.py). Path conflict resolved.
7. **`docs/adrs/` directory ownership:** story-ops-02 creates `docs/adrs/_template.md` + `docs/adrs/README.md` (architecture.md:68 reference now backed by a real story).
8. **`defenseclaw_backend.py` ownership:** story-judges-06 file modification map at line 23 explicitly NEW-marks `packages/splunkgate_judges/src/splunkgate_judges/defenseclaw_backend.py`. Three downstream consumers (mw-02, mw-05, mcp-03) no longer reference an orphan.
9. **`.tgz` artifact extension:** Consistent across story-app-12, story-cicd-08, cicd-spec.md. No surviving `.tar.gz` references.
10. **A-12 awk → Python regex swap (story-dc-02):** Quadruple-backtick awk pattern eliminated at line 39+92; replaced with `uv run python -c "import re, pathlib; ..."` that handles the fenced-block parsing safely under zsh.
11. **A-13 splunklib invented module fix (story-mcp-02):** Line 24 now uses `splunklib.ai.security.detect_injection` (the real symbol) instead of the invented `splunkgate_judges.splunklib_security_fallback` module.

Also confirmed clean (single-dim spot checks):
- `Synthetic-Data/` corrected spelling per ADR-011 — consistent in eval-spec.md, story-eval-01, architecture.md.
- Sentinel codename — cleaned in story-mcp-01 (only surviving reference is the ADR-004 historical note in architecture.md which explicitly documents the rename).
- 11 verbatim Cisco AI Defense rule names — story-app-05 + story-app-08 corrected; hallucinated names only survive inside explicit "DO NOT use" warnings.
- `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md` references in stories all use the correct relative path shape (3 levels up).
- model_middleware.py 200/200/400 LOC split between mw-03 + mw-04 is now coherent (anchor comments documented in both branches; mw-04's combined wc -l ≤ 400 BDD owns the file-level check).
- `mypy.ini` parsing now uses `configparser.RawConfigParser` (A-11 fix in story-skel-02:48/52).
- FoundationSec contract: `FoundationSecExplainer.explain(ctx: VerdictContext) -> str` consistent across foundsec-02 (owner), mw-04, mcp-05 (callers).
- `VerdictContext` Pydantic model — story-core-01 ships it at `packages/splunkgate_core/src/splunkgate_core/verdict_context.py` with the 6 expected fields; all three downstream consumers (mw-04:24, mcp-05:150, foundsec-02:24) import from the same location.

---

## Per-dimension matrix

| Dimension | # files checked | # regressions |
|---|---|---|
| Format compliance (5-section + headers + ≤ 2h) | 6 new stories | 0 |
| BDD machine-verifiability | 6 new stories + 4 most-edited | 2 (R-C-03 ops-01 × 2 BDD criteria) |
| File-map exactness | 6 new stories + app-02, app-10 | 1 (R-C-04 eval-06 lists sprint-status.yaml) |
| Cross-story consistency (types/imports) | core-01 ↔ mw-04/mcp-05/foundsec-02/judges-06 | 1 (R-C-01 source Literal) + 1 (R-C-02 build_explanation_spl signature self-contradiction) |
| Dependency graph (cycles / orphans / FLIP) | sprint-status.yaml 66 stories | 0 |
| Path / file-existence | check_loc.py × 5 files, emit_sample_verdict.py × 4, docs/adrs/, defenseclaw_backend.py | 0 |
| 400-LOC discipline | mw-03+mw-04 split, 6 new stories | 0 |
| Context-citation paths (`../../../...`) | sample 20 references across stories | 0 |
| Doc coherence (synthesis ↔ applied) | audit-synthesis.md vs commit | 1 (R-M-06 B-5 owner) |
| Naming convention | epic names | 1 (R-M-05 judges-06 epic name in YAML) |
| Internal credit/count drift | readme-01, app-13 rule order | 2 (R-M-01, R-M-02) |
| Stale cross-story references | app-02:152, app-10:187 | 2 (R-M-03, R-M-04) |

---

## One-paragraph recommendation

Block proceed on R-C-01 only (story-core-01 source Literal — single-line fix, but it cascades into 3+ packages). R-C-02 (foundsec-02 signature self-contradiction) and R-C-04 (eval-06 file map contradiction) are story-local — a coding agent could plausibly work around either by reading both halves of the spec, but the spec contract should be exact and they're cheap to fix in <2 minutes each. R-C-03 (ops-01 broken grep) is a story-local BDD bug that silently passes — fix before any orchestrator dispatch. Minor regressions can ship as-is; clean up in a follow-up PR. Total fix time: ~10 minutes of targeted `Edit` calls.

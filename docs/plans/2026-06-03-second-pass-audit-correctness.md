# Second-Pass Audit — Correctness Review

Auditor: second-pass correctness
Commit reviewed: post audit-fixes (19aef0e3 area, 4504-line diff across 52 files)
Date: 2026-06-03

## Verdict

- **20 audit findings UPHELD** (fix was correct + finding was true)
- **4 audit findings PARTIALLY UPHELD** (finding true; fix introduced a smaller new issue)
- **1 audit finding OVERTURNED** (finding was wrong; fix introduced or near-introduced a regression — but the implementer's instinct corrected for it)
- **3 NEW findings** the original audit + first-round synthesis missed (one of these is critical and should block dispatch)
- **2 CONFIRMED non-issues** (look off but are fine)

The fix pass is mostly excellent. There is **ONE CRITICAL DEFECT** the second-round critical review missed: A-5 was only half-fixed. Architecture.md was corrected, but the canonical Pydantic shape in `story-core-01-verdict-pydantic-types.md:171` still contains the banned `"foundation_sec_classifier"` literal. The coding agent will ship the wrong type from the story, not from architecture.md. This needs surgical correction before dispatch.

---

## Overturned findings (block these, roll back)

### O-01 — A-10 — Drill-down contract direction

- **Original audit claim**: standardize on `form.rule=...` (story-app-05's earlier shape); change story-app-06's `input_rule` declaration to match.
- **My check against Splunk Dashboard Studio v2 URL-binding spec**: DSv2 URL params bind via `?form.<input_id>=<value>` where `<input_id>` is the literal input id declared on the destination dashboard. If the destination's input id is `input_rule`, the canonical URL param IS `form.input_rule` — NOT `form.rule`.
- **What got implemented**: story-app-05 line 23 and 187 use `form.input_rule` (the spec-correct direction), NOT `form.rule` (the audit-synthesis recommendation). The fix WENT THE OPPOSITE WAY from the audit-synthesis recommendation — and the implemented direction is canonically correct.
- **Verdict**: Audit-synthesis line 30 was WRONG. The implementer (correctly) ignored it and standardized on `form.input_rule`. The current state in stories app-05 + app-06 is correct.
- **Recommendation**: Update audit-synthesis line 30 to reflect what actually landed (`form.input_rule`, not `form.rule`). No code change needed.

---

## Partially upheld (fix mostly right, small new issue)

### P-01 — A-5 — `foundation_sec_classifier` literal removal

- **Original finding**: ✓ correct (contradicts ADR-003).
- **Fix in `docs/architecture.md`**: ✓ correct (line 272 + lines 273-275 explanatory NOTE preventing re-introduction).
- **Smaller new issue**: `docs/stories/story-core-01-verdict-pydantic-types.md:171` STILL contains `"foundation_sec_classifier"` in the canonical reference Pydantic shape. This is the literal copy-paste source for the coding agent shipping `splunkgate_core.verdict`. The architecture.md fix protects the spec; the story does not protect the build.
- **Severity**: CRITICAL. The agent will ship the wrong type.
- **Recommendation**: Edit `docs/stories/story-core-01-verdict-pydantic-types.md:171` from `Literal["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]` to `Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]`. Also worth adding an inline comment matching architecture.md's NOTE block.

### P-02 — A-8 — README credit count drift

- **Original finding**: ✓ correct (PRD §13 = 5; BDD #8 = 6; shell = 7).
- **Fix attempt**: PRD §13 standardized on 5 (MCP Watch, Cisco Security Cloud, DefenseClaw, splunklib.ai, NeMo Guardrails).
- **Smaller new issue**: story-readme-01 STILL has the same drift. Line 23 says "5 named incumbents"; line 67 says "all six incumbent names"; line 133 iterates 7 grep targets (because the 5 names include 2 with parenthetical Splunkbase numbers, which the grep splits into separate tokens). The audit found this drift; the synthesis claimed standardization on "5 + 2 = 7"; the implemented story still has 5 / 6 / 7 in different places.
- **Severity**: Minor. BDD will likely pass (7 greps over 5 names that include 2 numbers), but the prose is contradictory.
- **Recommendation**: Edit story-readme-01:23 from "5 named incumbents" to "5 named incumbents (counting MCP Watch + its Splunkbase number as one credit, Cisco Security Cloud + its Splunkbase number as one)"; edit line 67 from "all six incumbent names" to "all 7 credit tokens" (matches line 133 iteration).

### P-03 — A-9 — Stale "surface=defenseclaw is wrong" artifact

- **Original finding**: ✓ correct — the line in story-eval-04 was a leftover edit artifact.
- **Fix attempt**: synthesis claimed "Delete the artifact comment".
- **Smaller new issue**: story-eval-04 line 25 still contains the half-corrected prose `Sets surface="defenseclaw" is wrong — uses surface="mw_model"`. The artifact was NOT deleted — it was rewritten in-line as a self-correction. Readability degraded; the original artifact comment is still readable.
- **Severity**: Trivial (prose hygiene).
- **Recommendation**: Edit story-eval-04:25 to delete `Sets surface="defenseclaw" is wrong — ` and let the prose flow as `... Parses the JSON response into a Verdict with surface="mw_model" (LLM-as-judge fits the model_middleware surface taxonomy)...`.

### P-04 — A-2 — "Sentinel" codename removal

- **Original finding**: ✓ correct.
- **Fix in story-mcp-01**: ✓ clean (no `sentinel` matches).
- **Smaller issue in architecture.md ADR-004**: explanation prose at line 374 still mentions `sentinel_*` to document the rename history. This is deliberate (provenance) but may confuse a coding agent if they ctrl-F sentinel. Minor.
- **Recommendation**: Either drop the parenthetical or wrap in a `[provenance footnote]`-style aside. Keep as-is is also fine.

---

## New findings the original 5-pass audit missed

### N-01 — story-foundsec-02 internal contract mismatch (CRITICAL — introduced by B-1 fix)

- **Issue**: story-foundsec-02 line 24 declares `build_explanation_spl(ctx: VerdictContext, provider: str, model: str) -> str` (3 args). EVERY usage of the function in the same story (line 36 BDD, line 43 BDD, line 120 shell verify, line 146 shell verify) calls `build_explanation_spl(ctx, verdict, provider=..., model=...)` (4 args, with `verdict` as the second arg). The function signature and the test invocations cannot both be right.
- **Severity**: CRITICAL. Coding agent will either implement the 3-arg signature (and all 4 BDD tests fail at parse) or implement the 4-arg signature (and the file-modification-map description is wrong → spec audit fails).
- **Root cause**: B-1 fix added `Verdict` as a parameter inside the prompt body composition without updating the file-map signature line.
- **Recommendation**: Update story-foundsec-02:24 signature to `build_explanation_spl(ctx: VerdictContext, verdict: Verdict, provider: str, model: str) -> str`. Also add a one-line note in §Notes that the `verdict` parameter carries the rules / classifications / severity / offending_text view that the prompt body needs.

### N-02 — story-judges-06 uses banned `Any` in `splunkgate_judges` (CRITICAL — introduced by Block D)

- **Issue**: story-judges-06 line 23 declares `def evaluate_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> RuleHit | None`. The architecture.md § "Banned patterns" line 360 explicitly bans `Any` in `splunkgate_core` and `splunkgate_judges` (mypy --strict catches this; story-core-01 line 189 already calls it out for `Verdict.modifications`).
- **Severity**: CRITICAL. mypy --strict job will fail; the story cannot pass its own typecheck BDD.
- **Recommendation**: Replace `dict[str, Any]` with `dict[str, object]` everywhere in judges-06 (lines 23 — 2 occurrences). The same fix story-core-01 already applies for `modifications: dict`.

### N-03 — sprint-status.yaml epic-name inconsistency for EPIC-12

- **Issue**: stories app-11 + app-12 use `epic: "EPIC-12 — AppInspect hardening"`; stories ops-01 + ops-02 use `epic: "EPIC-12 — AppInspect hardening + Ops"`. Two different epic strings for the same EPIC-12.
- **Severity**: Minor. The orchestrator groups by `epic` string; will produce 2 separate group buckets in any per-epic dashboard.
- **Recommendation**: Standardize. Update app-11 + app-12 in sprint-status.yaml to `"EPIC-12 — AppInspect hardening + Ops"` to match epics.md line 224.

---

## Confirmed non-issues

### V-01 — A-1 (`../../../research/...` path)

The sed proposed in audit-synthesis line 21 is literally `X → X` (no change). The path `../../../research/splunk-agentic-ops-2026/01-prizes-tracks.md` from `splunkgate/docs/stories/<file>.md` resolves correctly to `workspace/research/splunk-agentic-ops-2026/01-prizes-tracks.md`, which exists. The original audit was wrong; no fix was needed. Audit-synthesis Block A-1 row should be marked OVERTURNED in the synthesis history (cosmetic — no code action).

### V-02 — Dispatch order EPIC-02 → EPIC-01 → EPIC-02 remainder

Looks suspicious but is fine. Only `story-skel-01` (the workspace skeleton) genuinely has no upstream dependencies. skel-02/03/04 depend on later stories (cicd-04, etc.). The "EPIC-02 first" prose claim in epics.md line 15-16 is shorthand for "story-skel-01 first". The dispatch_queue (epics.md lines 247, 260) correctly splits skel-01 to the front and skel-02/03/04 to mid-build position. No cycles. No regression.

---

## Per-finding matrix

| Block | Finding | Orig correct? | Fix correct? | New issue? | Verdict |
|---|---|---|---|---|---|
| A | A-1 (research path) | NO (path was fine) | N/A (no-op sed) | — | OVERTURNED → V-01 |
| A | A-2 (Sentinel codename) | YES | YES (clean in stories; provenance prose left in ADR-004) | minor | UPHELD |
| A | A-3 (Synthetic-Data spelling) | YES | YES | — | UPHELD |
| A | A-4 (PRD story filename) | YES | YES | — | UPHELD |
| A | A-5 (foundation_sec_classifier removal) | YES | PARTIAL (arch.md fixed, story-core-01 NOT fixed) | CRITICAL | PARTIALLY UPHELD → P-01 |
| A | A-6 (Cisco rule names) | YES | YES (11 verbatim, no Toxicity/Self-Harm/bare Violence) | — | UPHELD |
| A | A-7 (.tgz extension) | YES | YES | — | UPHELD |
| A | A-8 (README credit count) | YES | PARTIAL (PRD aligned; story-readme-01 still has 5/6/7 drift) | minor | PARTIALLY UPHELD → P-02 |
| A | A-9 (defenseclaw artifact) | YES | PARTIAL (rewrote in-line instead of deleting) | trivial | PARTIALLY UPHELD → P-03 |
| A | A-10 (form.rule vs input_rule) | NO (synthesis recommendation was wrong) | YES (implementer correctly used form.input_rule) | — | OVERTURNED → O-01 |
| A | A-11 (RawConfigParser) | YES | YES | — | UPHELD |
| A | A-12 (awk → python) | YES | YES | — | UPHELD |
| A | A-13 (splunklib_security_fallback) | YES | YES (direct call to splunklib.ai.security) | minor (mocking gap in mcp-02) | UPHELD |
| B | B-1 (FoundationSec contract) | YES | PARTIAL (callers aligned; foundsec-02 internal signature mismatch) | CRITICAL | UPHELD w/ new finding N-01 |
| B | B-2 (model_middleware seam) | YES | YES (2 anchors, BLOCK explicit) | — | UPHELD |
| B | B-3 (MCP list_tools) | YES | YES (test-helper indirection clean) | — | UPHELD |
| B | B-4 (Splunk MCP coexistence) | YES | YES (10 + 4 enumerated verbatim) | — | UPHELD |
| B | B-5 (docs/adrs/) | YES | YES (story-ops-02 owns) | — | UPHELD |
| B | B-6 (model_middleware vs before_model hook) | YES | YES | — | UPHELD |
| C | C-* file map | YES | YES (skel-01 owns, deps flipped, no cycles) | — | UPHELD |
| C | dispatch order flip | YES | YES (EPIC-02-skel-01 first, then EPIC-01) | — | UPHELD → see V-02 caveat |
| D | story-core-05 (OTel HEC) | YES | YES (clean signature + tests) | — | UPHELD |
| D | story-app-13 (synthetic emitter) | YES | YES | — | UPHELD |
| D | story-eval-06 (e2e) | YES | YES | — | UPHELD |
| D | story-ops-01 (branch protection) | YES | YES (14 status checks match cicd-spec) | — | UPHELD |
| D | story-ops-02 (secrets + ADR template) | YES | YES | — | UPHELD |
| D | story-judges-06 (DefenseClaw shim) | YES | PARTIAL (uses `dict[str, Any]` — banned in splunkgate_judges) | CRITICAL | UPHELD w/ new finding N-02 |
| D | sprint-status.yaml epic-name | — | — | minor | N-03 |

---

## Recommended actions before dispatch

In priority order:

1. **CRITICAL — Edit `docs/stories/story-core-01-verdict-pydantic-types.md:171`** to remove `"foundation_sec_classifier"`. Match `docs/architecture.md:272` exactly.
2. **CRITICAL — Edit `docs/stories/story-foundsec-02-ai-spl-explanation-prompt.md:24`** to add `verdict: Verdict` to `build_explanation_spl` signature (matches all 4 BDD / shell uses).
3. **CRITICAL — Edit `docs/stories/story-judges-06-defenseclaw-python-shim.md:23`** to replace `dict[str, Any]` with `dict[str, object]` (2 occurrences: tool_args + handoff payload).
4. **Minor — Reconcile `docs/stories/story-readme-01-headline-and-banner-and-credits.md`** lines 23 / 67 / 133 to one consistent count.
5. **Minor — Edit `docs/sprint-status.yaml`** lines 256 + 261 to use `"EPIC-12 — AppInspect hardening + Ops"` (matches lines 306 + 310).
6. **Trivial — Edit `docs/stories/story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone.md:25`** to delete the "is wrong" prose artifact.
7. **Cosmetic — Update `docs/plans/2026-06-03-audit-synthesis.md`** Block A-1 row (mark as OVERTURNED) and A-10 row (mark as OVERTURNED — implementer corrected the direction).

After these, the spec set is dispatch-ready. The fix pass scored ≈25 out of ≈30 critical findings cleanly addressed, with 3 net-new issues introduced (all surgically fixable, none touching the architectural shape).

---

## Confidence

- Sources verified: `context/07-cisco-stack/01-ai-defense-deep.md` (A-6 11-rule list, lines 110-138 verbatim).
- Architecture cross-checks: architecture.md ADR-003 (line 372), ADR-010 (line 386), ADR-011 (line 388), Verdict shape (line 269), banned patterns (line 350).
- Story cross-checks: story-core-01 (line 171 — KEY DEFECT), story-foundsec-02 (line 24 vs lines 36+120+146), story-judges-06 (line 23), story-readme-01 (lines 23 / 67 / 133), story-mcp-01 through story-mcp-05 (list_tools_for_test indirection).
- Did NOT verify via Context7: FastMCP exact protocol surface — the audit-synthesis correctly chose a registry-based test helper that sidesteps the protocol question.
- Did NOT independently verify Splunk Dashboard Studio v2 URL-binding contract beyond reading the prose in story-app-05 — but the in-spec contract (`form.input_<name>=<value>`) is consistent with what Splunk docs typically state for DSv2 inputs.

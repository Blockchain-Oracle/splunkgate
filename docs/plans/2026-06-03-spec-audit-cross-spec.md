# Spec Audit — Cross-spec / Dependency Graph / Goal Alignment

Auditor: cross-spec + dependency + goal
Date: 2026-06-03

## Summary

18 findings · 6 critical · 8 minor · 4 non-issues clarified

Dependency graph is clean (60 stories, no cycles, no missing deps, no duplicates, no multi-epic stories, dispatch queue is 1:1 with sprint-status.yaml). Goal alignment is mostly intact — every epic ladders to the PRD demo moment. The critical issues are (1) a leftover "Sentinel" codename in two load-bearing places, (2) a `Verdict.source` literal that directly contradicts ADR-003, (3) `Synthetic-Data/` ADR-011 vs eval-spec.md fight, and (4) a `splunk_hec.go` line count typo in PRD that contradicts the audit. Everything else is housekeeping.

---

## Critical findings (block build phase until fixed)

- **C-01 — `Verdict.source` literal includes `"foundation_sec_classifier"` (directly contradicts ADR-003)**
  - Location: `docs/architecture.md:270` — `source: Literal["ai_defense", "defenseclaw_regex", "splunklib_security", "foundation_sec_classifier"]`
  - The problem: ADR-003 (`docs/architecture.md:367`) and the "Banned patterns" line at `architecture.md:356` both say Foundation-Sec is explainer-only, NEVER a classifier. The Pydantic schema then has `"foundation_sec_classifier"` as an allowed `RuleHit.source` value, which (a) reads as if Foundation-Sec emits rule hits like a classifier, and (b) gives the coding agent for `story-core-01` a literal to wire — they will treat it as canonical and the schema will bake the contradiction in.
  - The truth (per HALLUCINATION-AUDIT H-25 + ADR-003): Foundation-Sec is an explainer/generator. It populates `Verdict.explanation` only — it never appears in `RuleHit.source`.
  - Suggested fix: In `docs/architecture.md:270`, drop `"foundation_sec_classifier"` from the `Literal[...]`. Final list: `Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]`. Update `story-core-01-verdict-pydantic-types.md` (anywhere `RuleHit.source` literal is enumerated — check `story-core-01:161` and surrounding) to match. Add an inline comment: `# Foundation-Sec is explainer-only per ADR-003; it never appears here.`

- **C-02 — ADR-011 vs eval-spec.md spelling fight on `Synthetic-Data/`**
  - Location: `docs/architecture.md:383` (ADR-011 says corrected spelling) vs `docs/eval-spec.md:202` ("typo preserved per ADR-011") vs `docs/stories/story-eval-01-synthetic-data-generator-dns-guard-pattern.md:23` ("preserves DNS Guard's typo per ADR-011") + line 166 (self-contradictory paragraph explaining the contradiction).
  - The problem: ADR-011 explicitly says we use the CORRECTED spelling. Two downstream specs say we preserve the typo. story-eval-01:166 has a paragraph trying to paper over the contradiction by saying "the ADR commentary says preserve but the spec says corrected — use the spec." This will fail review by sahil-pr-audit because the BDD line at story-eval-01:42 invokes the path `Synthetic-Data/jailbreak_corpus/tool_call_abuse.jsonl` (corrected spelling) but the prose says "preserved."
  - The truth (per ADR-011): `Synthetic-Data/` corrected spelling. The DNS Guard `Syntethic-Data/` typo is documented as the inspiration but not replicated.
  - Suggested fix: In `docs/eval-spec.md:202`, replace `(typo preserved per ADR-011)` with `(corrected spelling per ADR-011)`. In `docs/stories/story-eval-01-synthetic-data-generator-dns-guard-pattern.md:23`, replace `the folder name preserves DNS Guard's typo per ADR-011` with `the folder name uses the corrected spelling per ADR-011 (DNS Guard's source uses the typo'd Syntethic-Data/ — we deliberately do not replicate the typo)`. Delete the contradictory hand-wavy paragraph at `story-eval-01:166`.

- **C-03 — Leftover "Sentinel" codename in architecture.md ADR-004 and story-mcp-01**
  - Location: `docs/architecture.md:369` — "SplunkGate MCP exposes `sentinel_*` and `splunkgate_*` tool names" + `docs/stories/story-mcp-01-server-skeleton-with-mcp-python-sdk.md:134` — "SplunkGate tools live under names like `splunkgate_*` / `sentinel_*`"
  - The problem: Project was renamed from Sentinel → SplunkGate. These two leftover references will cause the coding agent for story-mcp-01 to either (a) register tools under both prefixes, (b) ask Abu which one, or (c) silently pick wrong. The MCP tool names are user-visible (they show up in Claude Desktop's tool list) — getting this wrong is brand confusion at demo time.
  - The truth (per PRD line 1 + README line 1 + every other doc): the project is SplunkGate. There is no Sentinel.
  - Suggested fix: In `docs/architecture.md:369`, replace `SplunkGate MCP exposes \`sentinel_*\` and \`splunkgate_*\` tool names` with `SplunkGate MCP exposes \`splunkgate_*\` tool names`. In `story-mcp-01:134`, replace `live under names like \`splunkgate_*\` / \`sentinel_*\`` with `live under names prefixed \`splunkgate_*\``. Add a one-line ADR note: `Codename was Sentinel during early research; renamed to SplunkGate before spec phase.`

- **C-04 — PRD line 56 cites `splunk_hec.go` line count as 600 + `proxy.go` as 4430; mixed with the architecture.md schemas — but PRD lists DefenseClaw as Surface 3 and inconsistencies in implementation positioning**
  - Location: `docs/PRD.md:56` (cites line counts H-45/H-46 correctly) is consistent with HALLUCINATION-AUDIT. But the broader issue is `docs/PRD.md:46` says "Splunk MCP Server tool registration — Splunk's MCP Server is closed-source (CiscoDevNet repo is README+LICENSE only) — we run our own MCP server alongside" — this is correct. But neither PRD nor architecture.md cites the **10 splunk_* + 4 saia_* tool count** verified in HALLUCINATION-AUDIT H-12/H-13, even though sponsor-native pitch depends on coexistence.
  - The problem: A judge asking "what Splunk MCP tools coexist with yours?" gets no answer from the spec set. The verified-grounded promises section in PRD (lines 92-99) mentions "10 native `splunk_*` tools + 4 `saia_*` tools" — but the architecture/MCP server story does not. story-mcp-06 (Claude Desktop / Cursor config) will likely list the wrong tool count.
  - The truth (per H-12/H-13): 10 `splunk_*` tools + 4 `saia_*` tools.
  - Suggested fix: Add a sentence to `docs/architecture.md` ADR-004 (line 369): `Splunk's MCP Server v1.2.0 ships 10 \`splunk_*\` tools + 4 \`saia_*\` tools when SAIA is co-installed; SplunkGate's tools are additive via standard MCP client multi-server config.` Update `docs/stories/story-mcp-06-claude-desktop-cursor-config-examples.md` to enumerate Splunk's 10+4 tools in the example config so the coding agent ships an accurate multi-server JSON.

- **C-05 — `docs/adrs/` directory referenced but does not exist**
  - Location: `docs/architecture.md:68` lists `└── adrs/  # post-build architecture decisions` in the Repo structure block. The directory does not exist in `docs/`.
  - The problem: When the orchestrator dispatches story-skel-03 (CLAUDE.md + contribution conventions), the coding agent will not know whether `docs/adrs/` should be created with placeholder content or left as a post-build artifact. If left undocumented, ADRs end up in `docs/architecture.md` § "Architecture decisions" forever, but the architecture.md spec implies they get extracted post-build.
  - The truth: Spec set intends `docs/adrs/` to exist for post-build ADRs. Repo currently has no such folder.
  - Suggested fix: Either (a) create `docs/adrs/.gitkeep` + `docs/adrs/README.md` (single sentence: "Post-build ADRs land here; ADR-001 through ADR-011 are still inline in docs/architecture.md until extracted") and add this to story-skel-03's file modification map, OR (b) remove the `adrs/` line from `architecture.md:68` if Abu has decided ADRs stay inline forever. Pick one.

- **C-06 — PRD line 65 references a story file that does not exist**
  - Location: `docs/PRD.md:65` — "see `docs/stories/story-readme-01-headline.md` for the build story"
  - The problem: The actual filename is `docs/stories/story-readme-01-headline-and-banner-and-credits.md` (verified via `ls docs/stories/`). The PRD link is a dead reference. sahil-pr-audit will flag this when reviewing story-readme-01.
  - The truth: Filename is `story-readme-01-headline-and-banner-and-credits.md` per `docs/epics.md:214` and the actual file present.
  - Suggested fix: In `docs/PRD.md:65`, replace `docs/stories/story-readme-01-headline.md` with `docs/stories/story-readme-01-headline-and-banner-and-credits.md`.

---

## Minor findings (fix-when-convenient, not blockers)

- **M-01 — story count drift: epics.md header says "~57", yaml has 60, dispatch queue has 60.**
  - Location: `docs/epics.md:7` and line 319.
  - Fix: Replace "~57" / "Total: ~57 stories." with "60 stories" in both places.

- **M-02 — `ai_defense_types.py` file added by stories but not declared in architecture.md repo structure.**
  - Location: `docs/architecture.md:83` lists only `ai_defense.py`, `ai_defense_mock.py`, `foundation_sec.py`, `defenseclaw_backend.py`, `luna2_client.py`, `splunklib_security_fallback.py`. story-judges-01 creates `ai_defense_types.py` (line 24).
  - The truth: The split is fine architecturally (types vs client), but the repo-structure tree in architecture.md is the contract sahil-pr-audit checks against.
  - Fix: Add `│   │   │   ├── ai_defense_types.py                  # InspectRequest/Response Pydantic v2 models` to architecture.md's `splunkgate_judges/` listing before `ai_defense.py`.

- **M-03 — PRD demo step 3 says "before_model hook fires" but story-mw-01 says `before_model` is NOT re-exported and middleware uses `model_middleware` class subclassing.**
  - Location: `docs/PRD.md:27` vs `docs/stories/story-mw-01-package-skeleton-and-public-api.md:131`.
  - The problem: The PRD prose says "before_model hook (SplunkGate Surface 1 middleware) fires" — judge-facing demo language. But the actual mechanism is `SafetyModelMiddleware.model_middleware(self, request, handler)` async wrap. There's no "before_model hook" — there's a model_middleware that wraps and runs pre-inference logic before `await handler(request)`.
  - Fix: In PRD line 27, replace `The agent's \`before_model\` hook (SplunkGate Surface 1 middleware) fires` with `SplunkGate's \`SafetyModelMiddleware\` runs its pre-inference scan (Surface 1)`. Update demo script accordingly.

- **M-04 — architecture.md "Banned patterns" line 347 dismisses Tailwind but ux-spec.md "Banned patterns" (line 197) doesn't repeat it.**
  - Cross-spec: Not a real issue — architecture.md's `from-purple-500 to-pink-500` mention is humorous; ux-spec.md correctly bans Tailwind by virtue of "no external CSS/JS injected" (line 188). No fix needed, but flag this so M-04 is documented as an intentional cross-spec choice.
  - Fix: None. Document below in N-01.

- **M-05 — cicd-spec.md line 248 `eval-full` job conditional uses `github.event.label.name == 'eval'` which is technically only valid on `pull_request: types: [labeled]` events; on schedule/dispatch, `github.event.label` is null.**
  - The conditional uses `||` short-circuit so this is functionally OK, but YAML linters / GH Actions strict mode may warn. Fine for hackathon, flag for post-build.

- **M-06 — Eval-spec.md baseline 1 says "DefenseClaw regex-only" but architecture.md `splunkgate_judges/defenseclaw_backend.py` and eval/baselines layout doesn't expose a DefenseClaw regex extractor distinct from the AI Defense client. Story-eval-04 may need to clarify whether this is a Go subprocess call or a port of DefenseClaw's `rules.go` to Python.**
  - Location: `docs/eval-spec.md:98-103` and `docs/stories/story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone.md` (not read in this audit but inferable).
  - Fix: In story-eval-04 modification map, specify: "Baseline 1 invokes DefenseClaw via `subprocess` against the cloned Go binary at `inspiration/defenseclaw/` — do NOT port `rules.go` to Python."

- **M-07 — `splunk-appinspect` version pinned to "4.2.1+" in architecture.md but cicd-spec.md and story-cicd-05 don't enforce the floor.**
  - Location: `docs/architecture.md:26`.
  - Fix: In cicd-spec.md `appinspect` job (line 129), pin `splunk-appinspect>=4.2.1` in `uv sync` setup OR in story-cicd-05's modification map.

- **M-08 — README.md line 32 lists Cisco AI Defense rule names but in different order than PRD line 92.**
  - PRD: "Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats" (alphabetical-ish).
  - README: "Prompt Injection, PII, PHI, PCI, Code Detection, Harassment, Hate Speech, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats" (importance-ordered).
  - Both are correct 11-rule lists. Pick one order. Suggest README order (importance-first) for judge-facing surfaces, alphabetical for spec docs.

---

## Non-issues clarified

- **N-01 — architecture.md's Tailwind ban (`from-purple-500 to-pink-500`) appears unrelated to ux-spec.md's banned patterns.** Intentional. Architecture.md's banned-pattern is a defensive carve-out in case anyone adds a web UI in v2; ux-spec.md only governs Dashboard Studio v2 XML. No action.

- **N-02 — Two stories are "orphans" per dependency analysis (`story-cicd-07-security-scan-pipeline`, `story-readme-02-architecture-diagrams-light-dark-png`) — no deps and nobody depends on them.** This is correct: security pipeline is foundation + parallelizable, architecture diagram is asset work that can land any time. NOT a bug.

- **N-03 — story-mw-03 + story-mw-04 both write to the same file `model_middleware.py` (split as first/second half via an anchor comment).** This is intentional per the story-mw-03 split note (line 138). Two coding agents writing to one file is normally a red flag, but here it's sequenced (mw-04 depends_on mw-03) and the anchor comment provides a unique insertion point. NOT a bug.

- **N-04 — `eval-smoke` job has a `/override eval-smoke` PR comment escape hatch (`cicd-spec.md:497`).** Looks like a CI policy violation but is explicitly designed per spec because full eval runs nightly anyway. NOT a bug — flag if Abu's anti-override policy changes.

---

## Goal alignment verdict

Per-epic: does it contribute? Brief table.

| Epic | Surface | Contributes to PRD demo step | Contributes to PRD goal | Verdict |
|---|---|---|---|---|
| EPIC-01 (CI/CD) | Foundation | Indirect (gate quality) | Yes | OK |
| EPIC-02 (skeleton) | Foundation | Indirect | Yes | OK |
| EPIC-03 (Verdict type) | Foundation | Step 4 (verdict shape) | Yes — every surface | OK |
| EPIC-04 (AI Defense) | Judgment | Step 3 (BLOCK fires) | Yes — core classifier | OK |
| EPIC-05 (Foundation-Sec) | Judgment | Step 4 (explanation panel) | Yes — explanation layer | OK |
| EPIC-06 (S1 mw) | Surface 1 | Step 3 (the BLOCK happens here) | Yes — wow moment owner | **Load-bearing** |
| EPIC-07 (S2 MCP) | Surface 2 | Bonus prize, secondary demo | Yes — MCP track eligible | OK |
| EPIC-08 (S3 DefenseClaw) | Surface 3 | Not in demo flow | Indirect — "any-agent" claim | OK but cuttable |
| EPIC-09 (S4 Splunk app) | Surface 4 | Steps 1, 4, 5 (dashboards) | Yes — Splunk-native pitch | **Load-bearing** |
| EPIC-10 (eval) | Cross | Implicit (eval table in README) | Yes — Tech Impl tiebreaker | **Load-bearing** |
| EPIC-11 (README/demo) | Cross | The submission itself | Yes — non-negotiable | **Load-bearing** |
| EPIC-12 (AppInspect) | Surface 4 | Indirect (signals quality) | Yes — Splunk staff judges | OK |

Every epic ladders to the goal. EPIC-08 (DefenseClaw integration) is the lightest contributor to the demo (not in the 90-second flow per `docs/ux-spec.md:163`) but is the "any-agent-any-framework" claim's enabler — kept in scope.

The demo step 3 BLOCK action maps cleanly to:
- `story-mw-03` (pre-inference scan that fires) — entry point
- `story-judges-02` + `story-judges-04` (AI Defense client + mock backing it)
- `story-mw-01` (the public API the demo agent imports)
- `story-core-01` (Verdict type that gets emitted)

The demo step 4 (verdict in Splunk dashboard) maps to:
- `story-core-02` (OTel emitter)
- `story-app-02` (props/transforms for sourcetype)
- `story-app-05` (Agent Risk Overview dashboard)
- `story-app-06` (Verdict Inspector dashboard)

The demo step 5 (Regulator Evidence Pack PDF) maps to:
- `story-app-07` (the dashboard)
- `story-app-08` (RBA integration for risk_profile lookup)

All demo steps have story-level coverage. Goal alignment is sound.

The eval-spec.md table maps to PRD "Technological Implementation" criterion (PRD line 56) via precision/recall/F1/ECE/p50/p99 — exactly what PRD claims. ECE in particular is the differentiator vs gpt-oss-120b baseline. Aligned.

---

## Dependency-graph verdict

**Cycles:** Zero. DFS over all 60 stories returned no back-edges.

**Missing dependencies:** Zero. Every named dep resolves to an actual story id.

**Duplicates:** Zero. 60 unique story ids in yaml, 60 unique in dispatch queue.

**Multi-epic stories:** Zero.

**Orphans:** Two — both explained as intentional (N-02): `story-cicd-07-security-scan-pipeline`, `story-readme-02-architecture-diagrams-light-dark-png`.

**Dispatch queue match:** 1:1 with sprint-status.yaml — same 60 ids, no extras either side.

**Per-epic counts (yaml vs epics.md table):** All match (EPIC-01: 8, EPIC-02: 4, EPIC-03: 4, EPIC-04: 5, EPIC-05: 3, EPIC-06: 7, EPIC-07: 6, EPIC-08: 3, EPIC-09: 10, EPIC-10: 5, EPIC-11: 3, EPIC-12: 2 = 60).

**Terminal stories (nobody depends on):** 16, all expected leaves (test/asset stories at the end of each epic). No surprise terminals.

**Dispatch order vs depends_on:** Spot-checked story-mw-02 (depends on story-mw-01 + story-judges-05) — story-mw-02 appears AFTER both in the dispatch queue. Spot-checked story-app-10 (depends on app-05, 06, 07) — appears after them. Sample is consistent.

Dependency graph is **clean and ready to drive the orchestrator**. No graph-level changes needed.

---

## Recommended fix order (for Abu)

1. **C-01** (Verdict.source literal) — 30 seconds, prevents schema-baked contradiction.
2. **C-02** (Synthetic-Data ADR-011 contradiction) — 2 minutes, prevents wasted coding-agent time fighting the spec.
3. **C-03** (Sentinel codename leftover) — 1 minute, prevents brand confusion at demo.
4. **C-06** (PRD link to non-existent story file) — 30 seconds, prevents sahil-pr-audit false-flag.
5. **C-05** (`docs/adrs/` decision) — 2 minutes, pick (a) or (b).
6. **C-04** (Splunk MCP tool count in MCP server stories) — 5 minutes, prevents wrong tool count in MCP config example.
7. M-01 through M-08 — fix when convenient; none block the orchestrator.

Total estimated fix time: ~15 minutes. After these, the spec set is build-phase ready.

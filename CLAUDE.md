# CLAUDE.md

SplunkGate — runtime AI agent safety net for Splunk/Cisco enterprises. 4 surfaces: middleware library, MCP server, DefenseClaw integration, Splunk app. Spec set lives in `docs/`. Verified domain corpus at `../context/`. Hackathon research at `../research/splunk-agentic-ops-2026/`.

## How to work

1. **Pick the next PENDING story** from `docs/sprint-status.yaml` whose `depends_on` are all `COMPLETE`.
2. **Read the story file end-to-end** (`docs/stories/story-<id>.md`) — BDD criteria + file modification map are the contract.
3. **Research before implementing.** If you're not 100% sure how a library/API behaves, check:
   - Context7 MCP (`mcp__plugin_context7_context7__resolve-library-id` → `query-docs`) — your first stop for any SDK/library.
   - `../context/` corpus — primary-source-grounded facts on Splunk/Cisco/MCP/OTel.
   - Web search for fresh PyPI/GitHub state when the corpus is silent.
   - Read actual library source (`uv pip show <pkg>` → site-packages) when docs lie.

   The spec can be wrong. The domain knowledge can be wrong. Verify before coding.

4. **Implement.** Write tests first (BDD criteria → pytest cases). Stay within the story's file modification map.
5. **No mocks in the hot path.** Deadline is not a barrier to quality. Tests use `respx` for outbound HTTP; production code talks to real services. If integration is hard, do the right thing.
6. **Branch, commit, PR.** `git checkout -b feat/<story-id>` → `git commit -s` → `gh pr create --fill`.
7. **Run the PR-review subagent** the moment the PR is up: invoke `pr-review-toolkit:review-pr`. Address blocking findings; reject noise with rationale in a PR comment.
8. **Merge** with `gh pr merge --squash --delete-branch` once review verdict is acceptable (and CI is green once CI exists).
9. **Update sprint-status** on `main`: flip the story to `COMPLETE`, commit, push. Move to next story.

## Autonomy

Don't ask permission for each PR. Decide and act. Surface to Abu only when something genuinely contradicts the spec or needs project-level judgment Abu hasn't already documented.

## Subagents

Use them as *research assistants* while you implement — not as parallel implementers. One story at a time, your focus on it; subagents for "check Context7 for X" or "find the latest PyPI version of Y" while you code.

## Hard rules (CI will enforce these once cicd-01 ships)

- Every source file ≤ 400 LOC (non-blank, non-comment).
- `ruff` clean monorepo-wide.
- `mypy --strict` clean for `packages/splunkgate_core/` and `packages/splunkgate_judges/`.
- No `Any` in `splunkgate_core` or `splunkgate_judges` — use `object` + `repr()`.
- No real credentials in code or fixtures. AI Defense mocks default to `mock=True`.
- No `verify=False` in production HTTP.
- Verdict shape lives in `packages/splunkgate_core/src/splunkgate_core/verdict.py`. `RuleHit.source` is `Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]` — Foundation-Sec NEVER classifies (ADR-003).
- Cisco AI Defense rule names verbatim per `../context/07-cisco-stack/01-ai-defense-deep.md`. Response field is `rules`, not `triggered_rules`.
- Sourcetype `cisco_ai_defense:splunkgate_verdict` (colocates with Splunkbase 7404).
- MCP spec `2025-11-25` (Stable).

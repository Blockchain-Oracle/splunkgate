# Story — DefenseClaw contribute-back: AI Defense Inspection API rule backend (upstream PR notes + fork branch)

**Status:** ⚠ **DEFERRED** (2026-06-05 per ADR-013). Upstream merge timing on the DefenseClaw project is outside our control and adds submission risk. The README's DefenseClaw credit + config-delta docs (story-dc-01) preserve the "depend, don't rebuild" framing without the upstream PR.

**ID:** story-dc-02-ai-defense-backend-upstream-pr
**Epic:** EPIC-08 — Surface 3: DefenseClaw integration
**Depends on:** story-dc-01-config-delta-docs-and-example
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As an** SplunkGate maintainer who consumes DefenseClaw downstream
**I want to** produce a complete contribute-back PR plan for adding the Cisco AI Defense Inspection API as a first-class **rule backend** in DefenseClaw's `internal/gateway/rules.go` (alongside the existing regex backend) — including PR title, description draft, the exact Go interface change, the test additions, the CHANGELOG entry, and a published fork branch the PR will be opened from
**So that** DefenseClaw's rule layer becomes a pluggable interface (regex + API + LLM judge) instead of a regex-only switch, SplunkGate can stop carrying a config delta long-term, and the hackathon submission demonstrates upstream-maintainer-quality work — not a vendor lock-in fork

---

## File modification map

This story produces **markdown and a fork-branch reference**, not Go source. The Go code lives in our DefenseClaw fork repo and is reviewed via the upstream PR — not in this monorepo. The story is "done" when the PR draft is published and reproducible from the notes.

Exact files the coding agent creates or modifies for this story:

- `integrations/defenseclaw/upstream-pr-notes.md` — NEW — full PR plan document: (1) PR title (≤ 70 chars), (2) PR description draft (rendered markdown), (3) the proposed Go interface change as a unified-diff code block against `internal/gateway/rules.go`, (4) test plan as a unified-diff code block against `internal/gateway/rules_test.go`, (5) CHANGELOG entry diff, (6) backwards-compatibility analysis (the existing regex path stays default; the new backend is opt-in via `policies/guardrail/<profile>/rule_backend.yaml` selector), (7) the upstream-consumer use case section explicitly naming SplunkGate ("SplunkGate (https://github.com/<our-fork>/splunkgate) is the first downstream consumer relying on this interface — calling AI Defense from DefenseClaw avoids re-implementing the client in every consumer"), (8) maintainer-checklist matching cisco-ai-defense/defenseclaw's `CONTRIBUTING.md`
- `integrations/defenseclaw/upstream-pr-checklist.md` — NEW — operator checklist for actually opening the PR: fork URL slot, branch name (`feat/rules-ai-defense-backend`), `git push -u origin feat/rules-ai-defense-backend`, `gh pr create` command with `--repo cisco-ai-defense/defenseclaw --draft --title "<title>" --body-file integrations/defenseclaw/upstream-pr-notes.md`, post-open follow-up steps (assign reviewers from CODEOWNERS, link the SplunkGate hackathon repo)
- `integrations/defenseclaw/upstream-fork-ref.yaml` — NEW — a 5-field YAML pin: `fork_repo`, `fork_branch`, `upstream_repo`, `upstream_base_branch`, `pr_url` (filled in once the draft PR is opened, otherwise the string `"PENDING"`). This is the machine-readable artifact downstream tooling (and `sahil-pr-audit`) reads to verify the PR exists
- `integrations/defenseclaw/tests/test_upstream_pr_notes.py` — NEW — ≥ 10 behavioral tests against the upstream-pr-notes markdown: (a) PR title is ≤ 70 chars, (b) description contains the literal string `"AI Defense Inspection API"`, (c) description contains a fenced ```diff``` code block referencing `internal/gateway/rules.go`, (d) description contains a fenced ```diff``` code block referencing `internal/gateway/rules_test.go`, (e) description mentions SplunkGate as the upstream-consumer use case, (f) CHANGELOG entry diff is present, (g) interface name in the diff is `RuleBackend` (the proposed name), (h) the proposed interface has exactly two methods: `Scan(ctx, text, toolName) ([]RuleFinding, error)` and `Name() string`, (i) backwards-compatibility section explicitly states existing `regex` backend remains default, (j) upstream-pr-checklist.md exists and references a `feat/rules-ai-defense-backend` branch
- `integrations/defenseclaw/tests/test_upstream_fork_ref.py` — NEW — ≥ 4 behavioral tests against the fork-ref YAML: parses as YAML, all 5 fields present, `upstream_repo` is exactly `"cisco-ai-defense/defenseclaw"`, `upstream_base_branch` is `"main"`, `fork_branch` is `"feat/rules-ai-defense-backend"`

The coding agent must NOT write Go code into this monorepo. The actual Go diff (the `rules.go` change + `rules_test.go` additions) lives in the DefenseClaw fork repo — the story produces only the notes/diff documents and the fork-branch reference.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `awk 'NR==1' integrations/defenseclaw/upstream-pr-notes.md | sed 's/^# //' | awk '{print length}'` runs
Then  the output is ≤ 70 (PR title length cap)

Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `grep -cE "AI Defense Inspection API" integrations/defenseclaw/upstream-pr-notes.md` runs
Then  the count is ≥ 3 (title + description body + interface comment reference)

Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `grep -cE "internal/gateway/rules\\.go" integrations/defenseclaw/upstream-pr-notes.md` runs
Then  the count is ≥ 1

Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `grep -cE "RuleBackend" integrations/defenseclaw/upstream-pr-notes.md` runs
Then  the count is ≥ 2 (interface name appears in both the diff and the design discussion)

Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `grep -cE "[Aa]egis" integrations/defenseclaw/upstream-pr-notes.md` runs
Then  the count is ≥ 1 (upstream-consumer use case names SplunkGate)

Given integrations/defenseclaw/upstream-pr-notes.md exists
When  `uv run python -c "import re, pathlib; c=pathlib.Path('integrations/defenseclaw/upstream-pr-notes.md').read_text(); m=re.findall(r'^\`\`\`diff\$.*?^\`\`\`\$', c, re.MULTILINE|re.DOTALL); print(sum(len(b.splitlines()) for b in m))"` runs
Then  the count is ≥ 20 (at least two diff blocks: rules.go interface diff + rules_test.go diff; Python regex used in place of `awk` because zsh and bash both choke on the backtick-fence pattern in the awk script)

Given integrations/defenseclaw/upstream-fork-ref.yaml exists
When  `uv run python -c "import yaml; d=yaml.safe_load(open('integrations/defenseclaw/upstream-fork-ref.yaml')); assert d['upstream_repo']=='cisco-ai-defense/defenseclaw'; assert d['upstream_base_branch']=='main'; assert d['fork_branch']=='feat/rules-ai-defense-backend'; assert 'fork_repo' in d; assert 'pr_url' in d; print('OK')"` runs
Then  the output is "OK"

Given integrations/defenseclaw/tests/test_upstream_pr_notes.py exists
When  `uv run pytest integrations/defenseclaw/tests/test_upstream_pr_notes.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given integrations/defenseclaw/tests/test_upstream_fork_ref.py exists
When  `uv run pytest integrations/defenseclaw/tests/test_upstream_fork_ref.py -v` runs
Then  ≥ 4 tests pass and 0 fail

Given the §14 grep is run on changed markdown
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" integrations/defenseclaw/upstream-pr-notes.md integrations/defenseclaw/upstream-pr-checklist.md` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR (the SplunkGate-side PR, not the DefenseClaw upstream PR):

```bash
# Notes + checklist + fork-ref all exist
test -f integrations/defenseclaw/upstream-pr-notes.md
test -f integrations/defenseclaw/upstream-pr-checklist.md
test -f integrations/defenseclaw/upstream-fork-ref.yaml

# PR title under 70 chars
title=$(awk 'NR==1' integrations/defenseclaw/upstream-pr-notes.md | sed 's/^# //')
if [ ${#title} -gt 70 ]; then echo "title too long: ${#title}"; exit 1; fi

# Description references the right files + interface name + SplunkGate
grep -q "AI Defense Inspection API" integrations/defenseclaw/upstream-pr-notes.md
grep -q "internal/gateway/rules\.go" integrations/defenseclaw/upstream-pr-notes.md
grep -q "internal/gateway/rules_test\.go" integrations/defenseclaw/upstream-pr-notes.md
grep -q "RuleBackend" integrations/defenseclaw/upstream-pr-notes.md
grep -q -i "splunkgate" integrations/defenseclaw/upstream-pr-notes.md
grep -q -E "CHANGELOG" integrations/defenseclaw/upstream-pr-notes.md

# Diff blocks present
diff_lines=$(uv run python -c "
import re, pathlib
content = pathlib.Path('integrations/defenseclaw/upstream-pr-notes.md').read_text()
matches = re.findall(r'^\`\`\`diff\$.*?^\`\`\`\$', content, re.MULTILINE | re.DOTALL)
print(sum(len(m.splitlines()) for m in matches))
")
if [ "$diff_lines" -lt 20 ]; then echo "diff blocks too small: $diff_lines"; exit 1; fi

# Fork-ref schema
uv run python -c "
import yaml
d = yaml.safe_load(open('integrations/defenseclaw/upstream-fork-ref.yaml'))
assert d['upstream_repo'] == 'cisco-ai-defense/defenseclaw'
assert d['upstream_base_branch'] == 'main'
assert d['fork_branch'] == 'feat/rules-ai-defense-backend'
assert 'fork_repo' in d
assert 'pr_url' in d
print('OK')
"

# Tests pass
uv run pytest integrations/defenseclaw/tests/test_upstream_pr_notes.py integrations/defenseclaw/tests/test_upstream_fork_ref.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 14 (10 + 4)

# §14 clean on the markdown
grep -rE "(mock|fake|dummy|hardcoded|simulated)" integrations/defenseclaw/upstream-pr-notes.md integrations/defenseclaw/upstream-pr-checklist.md
# Must output nothing

# green-light passes
.claude/scripts/green-light.sh
# Must exit 0
```

---

## Notes for coding agent

- **This story produces a PR-NOTES document + a fork-branch reference, NOT Go source.** The actual `internal/gateway/rules.go` change (introducing the `RuleBackend` interface and an `AIDefenseBackend` implementation) lives in the DefenseClaw fork. The SplunkGate-side artifact is the plan — the agent does NOT clone DefenseClaw into this monorepo or write Go here. Per the file modification map: zero Go files are created in `splunkgate/`.
- **Per `../../../context/07-cisco-stack/06-defenseclaw-deep-read.md`, DefenseClaw is Apache-2.0; `internal/audit/sinks/splunk_hec.go` is exactly 600 lines, `internal/gateway/proxy.go` is exactly 4430 lines (verified multi-source).** The 600/4430 line counts are LOAD-BEARING: cite them in the PR description to demonstrate we read the source.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, we depend on DefenseClaw rather than rebuild — its HEC sink is production-grade with circuit breaker + retry + batch flush.** The PR description must lead with: "SplunkGate is the upstream-consumer use case. We rejected forking DefenseClaw and instead propose this interface so the rule layer becomes pluggable for everyone."
- **Per the upstream repo (commit `e1cb4d93`, v0.6.5), DefenseClaw currently only supports regex rule packs at the rule layer (no API backend); our PR adds AI Defense Inspection API as a backend.** The current state — verified in `../../../context/07-cisco-stack/06-defenseclaw-deep-read.md` §"Rule pack format" — is that `ScanAllRules(text, toolName)` iterates regex rules from YAML files at `policies/guardrail/<profile>/rules/*.yaml` (8 category files: c2.yaml, secrets.yaml, commands.yaml, enterprise-data.yaml, sensitive-paths.yaml, local-patterns.yaml, trust-exploit.yaml, cognitive.yaml). The hosted Cisco AI Defense Inspection API is wired separately in `internal/gateway/cisco_inspect.go` (318 lines) as a parallel inspection path, NOT as a rule backend. The proposed PR unifies these: a `RuleBackend` interface with `regex` and `ai_defense` implementations, selected via `policies/guardrail/<profile>/rule_backend.yaml`.
- **`adjustConfidence(toolName, finding)` is the novel tool-call inspection mechanic** in DefenseClaw (`internal/gateway/rules.go` lines 423–465). The PR must preserve this — the new `AIDefenseBackend.Scan` MUST also pass its findings through `adjustConfidence` so tool-name context (`knownExecTools`, `knownFileTools`, `knownWriteTools`, `knownReadTools`) keeps re-weighting confidence on AI-Defense findings too. Cite this in the PR description as "preserves existing tool-call confidence adjustment for backward compatibility".
- **Proposed Go interface (in the PR description as a unified diff against `internal/gateway/rules.go`):**
  ```go
  // RuleBackend abstracts the source of rule findings. The existing regex
  // backend reads policies/guardrail/<profile>/rules/*.yaml; the new
  // ai_defense backend forwards inspection to Cisco AI Defense.
  // adjustConfidence still runs on the returned findings regardless of
  // backend, so tool-name context still re-weights confidence.
  type RuleBackend interface {
      Scan(ctx context.Context, text, toolName string) ([]RuleFinding, error)
      Name() string
  }
  ```
- **PR title (≤ 70 chars):** suggested `feat(gateway): pluggable RuleBackend interface + AI Defense backend`. Exact 64 chars. The coding agent verifies the actual title used is ≤ 70.
- **CHANGELOG entry diff** in the PR description must follow DefenseClaw's existing CHANGELOG format (verified via `../../../context/07-cisco-stack/06-defenseclaw-deep-read.md` §"Why DefenseClaw matters" item 5 — references the existing changelog phrasing pattern `"The PreToolUse hook returns a permissionDecision: \"deny\" verdict on policy hits…"`).
- **Fork branch is `feat/rules-ai-defense-backend`.** Branch name is LOAD-BEARING because the `upstream-fork-ref.yaml` is the machine-readable artifact downstream tooling (and `sahil-pr-audit`) reads.
- **`pr_url` may be `"PENDING"`** in the fork-ref YAML when this story is first merged — the PR is opened as a draft after the SplunkGate-side merge. The follow-up commit fills in the real URL once the draft PR exists at e.g. `https://github.com/cisco-ai-defense/defenseclaw/pull/<n>`.
- **Backwards-compatibility section** in the PR description must explicitly state: (a) existing regex backend remains default; (b) zero-config existing deployments are unaffected; (c) the new selector lives in a new file `policies/guardrail/<profile>/rule_backend.yaml`, missing-file falls back to regex; (d) the existing `internal/gateway/cisco_inspect.go` AID path is unchanged and continues to operate as a parallel inspection step (not a rule-layer replacement).
- The coding agent does NOT open the upstream PR from this story execution — that's a manual operator step on the `upstream-pr-checklist.md` after the SplunkGate-side merge. The story is complete when the notes + checklist + fork-ref artifacts pass tests; whether the upstream PR is actually filed is tracked separately.

# Story — eval-smoke CI job: ~20 prompts via AI Defense mock client in < 60s

**ID:** story-cicd-06-eval-smoke-job
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-cicd-02-test-pipeline-pytest-respx
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent landing changes to the judgment layer, the middleware, or the MCP server
**I want to** every PR runs a ~20-prompt smoke subset of the eval harness against the AI Defense mock client in <60s and fails the PR if any expected verdict regresses
**So that** we catch end-to-end wiring breakage (judges → core → middleware → MCP) on every push without waiting for the nightly full eval, and we get cheap evidence that the four surfaces stay in sync

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/ci.yml` — UPDATE — append the `eval-smoke` job. Copy verbatim from `docs/cicd-spec.md` § "Concrete YAML skeleton" lines 141-151. `needs: [test]`, `timeout-minutes: 10` (script itself targets <60s; 10-min ceiling is for cold-start + uv sync overhead). Pass `AEGIS_AI_DEFENSE_MOCK=true` env var.
- `eval/pyproject.toml` — NEW — uv-workspace package metadata for the `eval` package (no runtime deps yet; dev deps from root). Listed as workspace member by cicd-01.
- `eval/src/aegis_eval/__init__.py` — NEW — `__version__ = "0.0.0"` placeholder
- `eval/scripts/__init__.py` — NEW — empty
- `eval/scripts/smoke.py` — NEW — runnable Python module (~150-200 LOC, under cap) that: (1) loads `eval/data/smoke_prompts.jsonl` (~20 prompts, each with `prompt`, `expected_verdict`, `expected_severity` fields); (2) for each prompt, calls a stub `judge(prompt) -> Verdict` function that wraps a respx-mocked HTTP call to the AI Defense Inspection API (mock URL `https://us.api.inspect.aidefense.security.cisco.com/v1/inspect`); (3) compares the returned `verdict` + `severity` against expected; (4) emits a JSON summary `{"total": 20, "pass": N, "fail": M, "duration_s": T}` to stdout; (5) exits 0 if `fail == 0 and duration_s < 60`, else exits 1. Honors `AEGIS_AI_DEFENSE_MOCK=true` (which is the only mode this story supports — live mode is a `NotImplementedError` here; EPIC-10 wires live mode).
- `eval/data/smoke_prompts.jsonl` — NEW — exactly 20 JSON-lines records. Sourced from: 10 from JailbreakBench `behaviors` subset (per `../../../context/01-threat-landscape/02-jailbreak-techniques.md`), 5 hand-curated PII leak prompts (`../../../context/01-threat-landscape/04-pii-and-data-leak-mechanics.md`), 5 benign prompts (negative controls). Each record: `{"id": "smoke-NNN", "prompt": "...", "expected_verdict": "BLOCK|ALLOW|MODIFY", "expected_severity": "HIGH|LOW|NONE_SEVERITY|MEDIUM", "category": "jailbreak|pii|benign"}`.
- `eval/tests/__init__.py` — NEW — empty
- `eval/tests/test_smoke.py` — NEW — pytest module with minimum 4 test cases: (a) `smoke.py` exits 0 when all 20 mocked verdicts match expected; (b) `smoke.py` exits 1 when one mocked verdict is wrong; (c) `smoke.py` exits 1 if duration > 60s (simulate via patched timer); (d) `smoke.py` raises `NotImplementedError` if `AEGIS_AI_DEFENSE_MOCK` is unset / not `"true"`. Uses respx to mock the AI Defense endpoint.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `eval/data/smoke_prompts.jsonl` exists and contains exactly 20 lines
When  `wc -l eval/data/smoke_prompts.jsonl` runs
Then  the count is exactly 20

Given each line of `eval/data/smoke_prompts.jsonl` is valid JSON
When  `python -c "import json; [json.loads(l) for l in open('eval/data/smoke_prompts.jsonl')]"` runs
Then  exit code is 0

Given the `AEGIS_AI_DEFENSE_MOCK=true` env var is set
When  `uv run python eval/scripts/smoke.py` runs
Then  exit code is 0
And   the run completes in < 60 seconds (verified via `time` wrapper)
And   stdout contains a JSON object with `"total": 20`, `"pass": 20`, `"fail": 0`

Given the env var is NOT set (or set to "false")
When  `uv run python eval/scripts/smoke.py` runs
Then  exit code is non-zero
And   stderr contains `NotImplementedError` or `live mode not wired in cicd-06`

Given a deliberately-broken prompt (e.g., expected_verdict mutated to a wrong value)
When  `uv run python eval/scripts/smoke.py` runs against the mutated dataset
Then  exit code is 1
And   stdout contains `"fail":` followed by a non-zero number

Given `uv run pytest eval/tests/test_smoke.py` runs
When  the run completes
Then  exit code is 0
And   stdout contains `4 passed`

Given the `eval-smoke` job runs on GitHub Actions
When  the workflow completes on a clean PR
Then  the job is green
And   `gh run view --json jobs --jq '.jobs[] | select(.name == "Eval smoke (fast subset)") | .conclusion'` outputs `success`

Given `wc -l eval/scripts/smoke.py | awk '{print $1}'` runs
When  the output is checked
Then  the value is < 400

Given the smoke prompts file content
When  `grep -c '"category": "jailbreak"' eval/data/smoke_prompts.jsonl` runs
Then  the count is exactly 10
And   `grep -c '"category": "pii"' eval/data/smoke_prompts.jsonl` is exactly 5
And   `grep -c '"category": "benign"' eval/data/smoke_prompts.jsonl` is exactly 5
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. Dataset is exactly 20 prompts, all valid JSON, correct category distribution
test "$(wc -l < eval/data/smoke_prompts.jsonl)" -eq 20
python -c "import json; [json.loads(l) for l in open('eval/data/smoke_prompts.jsonl')]"
test "$(grep -c '"category": "jailbreak"' eval/data/smoke_prompts.jsonl)" -eq 10
test "$(grep -c '"category": "pii"' eval/data/smoke_prompts.jsonl)" -eq 5
test "$(grep -c '"category": "benign"' eval/data/smoke_prompts.jsonl)" -eq 5

# 2. Script runs in mock mode, passes all 20, under 60s
START=$(date +%s)
AEGIS_AI_DEFENSE_MOCK=true uv run python eval/scripts/smoke.py | tee /tmp/smoke_out.json
END=$(date +%s)
test $((END - START)) -lt 60
python -c "import json; r=json.load(open('/tmp/smoke_out.json')); assert r['total']==20 and r['fail']==0, r"

# 3. Script refuses to run without the mock env var
if uv run python eval/scripts/smoke.py 2>&1 | grep -q "NotImplementedError\|live mode not wired"; then
  echo "live-mode guard fires correctly"
else
  echo "FAIL: live-mode guard missing"; exit 1
fi

# 4. Tests pass
uv run pytest eval/tests/test_smoke.py -v
uv run pytest eval/tests/test_smoke.py -q | grep -q '4 passed'

# 5. LOC under cap
test "$(grep -cvE '^\s*(#|$)' eval/scripts/smoke.py)" -lt 400

# 6. CI YAML wires the job
grep -q 'eval-smoke:' .github/workflows/ci.yml
grep -q 'AEGIS_AI_DEFENSE_MOCK=true' .github/workflows/ci.yml
grep -q 'eval/scripts/smoke.py' .github/workflows/ci.yml

# 7. Push and verify
git push origin HEAD
gh run watch --exit-status
```

All blocks must exit 0.

---

## Notes for coding agent

- Per `docs/cicd-spec.md` § "Failure mode handling" line 497, `eval-smoke` failure can be overridden by Abu commenting `/override eval-smoke` on the PR — but that override path lives in branch-protection config (manual, EPIC-02 documents it), not in this story.
- Per ADR-006 (`docs/architecture.md` § "Architecture decisions"), the AI Defense client defaults to mock; live calls require `AEGIS_AI_DEFENSE_API_KEY`. This story's `smoke.py` IS the mock contract — it uses respx to fake AI Defense responses keyed by prompt category (jailbreak → BLOCK/HIGH, pii → MODIFY/MEDIUM, benign → ALLOW/NONE_SEVERITY).
- The stub `judge(prompt)` function in `smoke.py` is intentionally minimal — it does NOT import from `aegis_judges` or `aegis_core` yet (those packages have only placeholder `__init__.py` from cicd-01/02). Instead, `smoke.py` defines its own local `Verdict`-shaped dict. When EPIC-04 lands real `aegis_judges.ai_defense.AiDefenseClient` + EPIC-03 lands real `aegis_core.verdict.Verdict`, story `story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone.md` rewrites `smoke.py` to use the real types. Add a `# TODO(EPIC-04): replace stub judge with aegis_judges.ai_defense.AiDefenseClient` comment.
- The 20-prompt dataset is sourced manually from JailbreakBench's `harmful_behaviors.csv` (10 prompts, take rows 1-10 for reproducibility; cite the JailbreakBench commit SHA in a JSONL `_provenance` field per row). PII corpus draws on Imprompter payloads per `../../../context/01-threat-landscape/04-pii-and-data-leak-mechanics.md`. Benign prompts: hand-craft to "What's the weather in Seattle?" etc.
- The 60-second budget is tight on cold GitHub runners. Tactics: (1) `respx.mock` intercepts all HTTP — no real network. (2) Sequential not parallel (parallelism adds asyncio overhead for 20 calls). (3) Cache nothing — keep the script stateless. If a future story needs more prompts (e.g., 50), bump the workflow timeout to 5 min but keep the smoke-budget assertion at 60s for the current 20.
- Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, `splunklib.ai.security.detect_injection` uses 9 regex patterns. This story's stub `judge` may shortcut to a regex match on the prompt text to assign mocked verdicts — that's an acceptable proxy. Story `story-judges-01-ai-defense-request-response-models.md` defines the real contract.
- The categorization counts (10+5+5=20) are LOAD-BEARING acceptance criteria. If a verification step shows a different count, the dataset is wrong, not the test.
- `smoke.py` must use `argparse` for `--dataset` flag (default `eval/data/smoke_prompts.jsonl`) so the test suite can pass a mutated dataset path for the failure-path test cases.
- The `time_s` measurement uses `time.perf_counter()` bookending the loop; exclude module-import time from the budget so cold-start doesn't dominate.
- Per `../../../context/01-threat-landscape/02-jailbreak-techniques.md`, JailbreakBench is the canonical eval source; do not invent prompts when the dataset has them. Cite JailbreakBench rows by `behavior_index` field for reproducibility.

# Story — JailbreakBench (PyPI) + AdvBench (git submodule) loaders → EvalPrompt

**ID:** story-eval-02-jailbreakbench-and-advbench-loaders
**Epic:** EPIC-10 — Eval harness
**Depends on:** story-eval-01-synthetic-data-generator-dns-guard-pattern
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** judge cross-referencing the Aegis eval results against the canonical jailbreak benchmarks
**I want to** see the harness load JailbreakBench (1,000 prompts) and AdvBench (520 prompts) via standard library loaders and feed them into the same `EvalPrompt` shape the synthetic corpus uses
**So that** the eval table's columns are comparable across canonical and custom datasets, and replication only requires installing the dev deps + initializing one git submodule

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `eval/src/aegis_eval/jailbreakbench.py` — NEW — loader that calls `jailbreakbench.read_dataset()` per the PyPI package's documented API, iterates the 100 harmful-behavior × 10-variant grid into 1,000 `EvalPrompt` records with `category="jailbreakbench"`, `expected_verdict="BLOCK"`, `expected_severity="HIGH"`, `source_citation="jailbreakbench:vX.Y:<behavior_id>:<variant_id>"`. Provides `load_jailbreakbench(limit: int | None = None) -> list[EvalPrompt]`. On `limit` non-None, returns the first `limit` records (used by the smoke job).
- `eval/src/aegis_eval/advbench.py` — NEW — loader that reads `inspiration/llm-attacks/data/advbench/harmful_behaviors.csv` (520 rows: `goal`, `target`) via stdlib `csv`, emits 520 `EvalPrompt` records with `category="advbench"`, `expected_verdict="BLOCK"`, `expected_severity="HIGH"`, `source_citation="advbench:zou-et-al-2023:row-<n>"`. Provides `load_advbench(limit: int | None = None) -> list[EvalPrompt]`. Raises `AdvBenchSubmoduleMissingError` with a clear remediation message if the submodule path is missing.
- `eval/src/aegis_eval/__init__.py` — UPDATE — re-export `load_jailbreakbench`, `load_advbench`, and the new `AdvBenchSubmoduleMissingError`.
- `eval/pyproject.toml` — UPDATE — add `jailbreakbench` to `[project.optional-dependencies].dev` (already lives there per `docs/architecture.md` § "Required external libraries").
- `.gitmodules` — UPDATE (or NEW) — register `inspiration/llm-attacks` as a submodule pointing at `https://github.com/llm-attacks/llm-attacks.git` pinned to commit `0f6244a` (the released revision used in Zou et al. 2023). If `.gitmodules` exists from earlier stories, append the new entry; do not modify existing entries.
- `eval/tests/test_jailbreakbench_loader.py` — NEW — ≥ 8 tests: `jailbreakbench` import works (or test xfails with documented skip-reason); `load_jailbreakbench()` returns >= 1000 records when no limit is set (use respx-style monkey-patch if PyPI dataset download isn't desired in unit tests — see Notes); `limit=5` returns exactly 5 records; every record validates as `EvalPrompt`; every record has `category="jailbreakbench"`, `expected_verdict="BLOCK"`, `expected_severity="HIGH"`; `source_citation` field is unique across the corpus (no duplicates); loading is deterministic (same order on repeat calls).
- `eval/tests/test_advbench_loader.py` — NEW — ≥ 6 tests: `load_advbench()` returns exactly 520 records when the submodule CSV exists; `limit=10` returns exactly 10 records; every record validates as `EvalPrompt`; every record has `category="advbench"`, `expected_verdict="BLOCK"`, `expected_severity="HIGH"`; missing submodule raises `AdvBenchSubmoduleMissingError` with the remediation string `"git submodule update --init inspiration/llm-attacks"` in the message; CSV row count assertion: `wc -l` on the file matches len(records) + 1 (header).
- `eval/tests/fixtures/advbench_sample.csv` — NEW — 10-row minimized AdvBench-shape CSV (header `goal,target` + 10 rows from the public release — copy verbatim from `inspiration/llm-attacks/data/advbench/harmful_behaviors.csv` first-10-rows; used by tests via monkeypatched path so unit tests don't depend on the submodule being initialized).

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the dev dependencies are installed (`uv sync --extra dev`)
When  `uv run python -c "import jailbreakbench; print('ok')"` runs
Then  exit code is 0 (PyPI package importable)

Given the git submodule is initialized: `git submodule update --init inspiration/llm-attacks`
When  `test -f inspiration/llm-attacks/data/advbench/harmful_behaviors.csv` runs
Then  exit code is 0

Given the JailbreakBench loader
When  `uv run python -c "from aegis_eval.jailbreakbench import load_jailbreakbench; ps=load_jailbreakbench(); print(len(ps))"` runs
Then  the printed integer is >= 1000

Given the JailbreakBench loader with limit=5
When  `uv run python -c "from aegis_eval.jailbreakbench import load_jailbreakbench; ps=load_jailbreakbench(limit=5); print(len(ps))"` runs
Then  the printed integer is exactly 5

Given the AdvBench loader with the submodule initialized
When  `uv run python -c "from aegis_eval.advbench import load_advbench; ps=load_advbench(); print(len(ps))"` runs
Then  the printed integer is exactly 520

Given the AdvBench loader and the submodule path missing
When  the loader is invoked against a non-existent path
Then  `AdvBenchSubmoduleMissingError` is raised with substring "git submodule update --init inspiration/llm-attacks"

Given every record returned by either loader
When  validated against the EvalPrompt schema
Then  zero validation errors

Given every JailbreakBench record
When  the `(category, expected_verdict, expected_severity)` triple is inspected
Then  it equals exactly `("jailbreakbench", "BLOCK", "HIGH")`

Given every AdvBench record
When  the `(category, expected_verdict, expected_severity)` triple is inspected
Then  it equals exactly `("advbench", "BLOCK", "HIGH")`

Given `uv run pytest eval/tests/test_jailbreakbench_loader.py eval/tests/test_advbench_loader.py -v`
When  it runs
Then  >= 14 tests pass and 0 fail

Given the loader source files
When  `uv run mypy --strict eval/src/aegis_eval/jailbreakbench.py eval/src/aegis_eval/advbench.py` runs
Then  exit code is 0

Given every modified or new file
When  wc -l is run
Then  each file is <= 400 LOC
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Dev deps installable
uv sync --extra dev
uv run python -c "import jailbreakbench"

# 2. Initialize the AdvBench submodule (idempotent)
git submodule update --init inspiration/llm-attacks
test -f inspiration/llm-attacks/data/advbench/harmful_behaviors.csv

# 3. JailbreakBench loader returns the documented 1000 prompts
count=$(uv run python -c "from aegis_eval.jailbreakbench import load_jailbreakbench; print(len(load_jailbreakbench()))")
[ "$count" -ge 1000 ] || { echo "FAIL: JailbreakBench returned $count, expected >= 1000"; exit 1; }

# 4. JailbreakBench limit kwarg works
count5=$(uv run python -c "from aegis_eval.jailbreakbench import load_jailbreakbench; print(len(load_jailbreakbench(limit=5)))")
[ "$count5" -eq 5 ] || { echo "FAIL: JailbreakBench limit=5 returned $count5"; exit 1; }

# 5. AdvBench loader returns exactly 520
adv_count=$(uv run python -c "from aegis_eval.advbench import load_advbench; print(len(load_advbench()))")
[ "$adv_count" -eq 520 ] || { echo "FAIL: AdvBench returned $adv_count, expected 520"; exit 1; }

# 6. Missing-submodule error message includes remediation
uv run python - <<'PY'
import os, tempfile
from aegis_eval.advbench import load_advbench, AdvBenchSubmoduleMissingError
with tempfile.TemporaryDirectory() as d:
    try:
        load_advbench(csv_path=os.path.join(d, "missing.csv"))
        raise SystemExit("expected AdvBenchSubmoduleMissingError")
    except AdvBenchSubmoduleMissingError as e:
        assert "git submodule update --init inspiration/llm-attacks" in str(e), e
print("OK")
PY

# 7. Every record validates
uv run python - <<'PY'
from aegis_eval.jailbreakbench import load_jailbreakbench
from aegis_eval.advbench import load_advbench
for p in load_jailbreakbench(limit=50) + load_advbench(limit=50):
    assert p.category in ("jailbreakbench", "advbench")
    assert p.expected_verdict == "BLOCK"
    assert p.expected_severity == "HIGH"
    assert p.source_citation
print("OK")
PY

# 8. Tests pass
uv run pytest eval/tests/test_jailbreakbench_loader.py eval/tests/test_advbench_loader.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 14

# 9. Strict typecheck
uv run mypy --strict eval/src/aegis_eval/jailbreakbench.py eval/src/aegis_eval/advbench.py

# 10. 400-LOC cap
for f in eval/src/aegis_eval/jailbreakbench.py eval/src/aegis_eval/advbench.py eval/tests/test_jailbreakbench_loader.py eval/tests/test_advbench_loader.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
echo "ALL CHECKS PASS"
```

---

## Notes for coding agent

- **Per `../../../context/01-threat-landscape/02-jailbreak-techniques.md` §10 (NIST 100-2e2025 line 3053)**: *"Datasets like JailbreakBench, AdvBench, HarmBench, StrongREJECT, AgentHarm, and Do-Not-Answer provide benchmarks for evaluating models' susceptibility to jailbreaks."* JailbreakBench and AdvBench are the two canonical baselines — get these landed before HarmBench or others.
- **Per `docs/eval-spec.md` § "Datasets"**: JailbreakBench is 100 harmful behaviors × 10 jailbreak variants = 1,000 prompts. AdvBench is 520 adversarial prompts from Zou et al. 2023 (`https://arxiv.org/abs/2307.15043`). The PyPI package `jailbreakbench` exposes `read_dataset()` — call **Context7** before implementing to confirm current API shape: `mcp__context7__resolve-library-id libraryName="jailbreakbench"` then `mcp__context7__query-docs context7CompatibleLibraryID="<id>" topic="dataset loading API" tokens=3000`.
- **Per `docs/architecture.md` § "Required external libraries"**: `jailbreakbench` ships as a dev dep (`uv add --dev jailbreakbench`). It is NOT in `aegis_core` or `aegis_judges` — only in `eval/`.
- **AdvBench license**: MIT (per the upstream `llm-attacks/llm-attacks` repo LICENSE). The submodule pattern keeps the data out of our git tree (we only pin a SHA) so we inherit license terms cleanly.
- **Per `../../../context/01-threat-landscape/02-jailbreak-techniques.md` §7 (GCG)**: AdvBench is the standard baseline Zou et al. used to demonstrate universal adversarial suffixes. Our eval reports AdvBench separately from JailbreakBench so judges can see both axes (curated harmful-behavior coverage vs. adversarial-suffix scaling).
- **The submodule URL is `https://github.com/llm-attacks/llm-attacks.git`** (NOT `llm-attacks/llm-attacks` — that's the org/repo path). Pin a fixed commit so dataset content is stable across runs. Use the commit released alongside the published paper to match the cited 520 prompts exactly.
- **Unit tests should not require network**: the `jailbreakbench` PyPI package downloads its dataset on first call. For unit tests, use the `fixtures/advbench_sample.csv` and a tiny in-memory JailbreakBench mock via `monkeypatch.setattr` against `jailbreakbench.read_dataset`. The full-corpus assertion runs in the integration test row, gated on a `--integration` pytest marker if needed.
- **Per `docs/eval-spec.md` § "Honesty bar"**: No "estimated" numbers. Either we ran the eval against the real corpus or we leave it blank. The loaders are the gate that makes real numbers possible.
- **EvalPrompt schema**: matches story-eval-01's definition. `id` should be deterministic (e.g., `f"jbb:{behavior_id}:{variant_id}"` for JailbreakBench, `f"advbench:{row_index}"` for AdvBench) so per-prompt verdicts in `eval/results/<sha>/per_dataset/*.json` are joinable across runs.
- **The `AdvBenchSubmoduleMissingError`** must subclass `aegis_core.errors.AegisError` (per coding standards, all errors derive from `AegisError`). Its `__init__` message must include the verbatim remediation command — that's what `sahil-pr-audit` greps for in the verification.
- Estimate breakdown: ~20 min Context7 + JailbreakBench loader, ~20 min AdvBench loader + submodule, ~30 min tests + fixtures, ~20 min strict mypy clean-up + verification.

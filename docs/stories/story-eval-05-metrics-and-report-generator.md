# Story — Metrics (P/R/F1/ECE) + latency (p50/p99) + cost + report.py → docs/eval-results.md

**ID:** story-eval-05-metrics-and-report-generator
**Epic:** EPIC-10 — Eval harness
**Depends on:** story-eval-02-jailbreakbench-and-advbench-loaders, story-eval-03-imprompter-payload-corpus-from-pdf, story-eval-04-three-baselines-defenseclaw-gptoss-aidefense-alone
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** judge opening the README and looking for the eval table that demonstrates SplunkGate measurably works
**I want to** see `docs/eval-results.md` rendered from real per-dataset JSON results with Precision, Recall, F1, ECE, p50/p99 latency, and $/1k verdicts per evaluator × dataset, alongside reliability diagrams (PNG) per evaluator
**So that** the tiebreaker "Technological Implementation" criterion has an unambiguous artifact — and the smoke variant runs in CI under 60 seconds so PRs never merge with a broken eval pipeline

---

## File modification map

The 400-LOC cap forces this story to split metrics across multiple files. Layout:

- `eval/src/splunkgate_eval/metrics.py` — NEW — pure classification metrics: `precision(y_true, y_pred) → float`, `recall(...)`, `f1(...)`, `specificity(...)`, `confusion_matrix(...)`, `expected_calibration_error(y_true, probas, n_bins=10) → float`. All functions take Python lists/iterables; numpy used for vectorized math (numpy is acceptable in `eval/` per `docs/architecture.md` § "Banned" — banned only in `splunkgate_core`/`splunkgate_judges`). No plotting in this file.
- `eval/src/splunkgate_eval/reliability.py` — NEW — `reliability_diagram(y_true, probas, n_bins=10, output_path: Path) → None` renders a matplotlib reliability diagram (calibration plot: predicted probability bin midpoint on x-axis, observed fraction-positive on y-axis, diagonal "perfectly calibrated" reference line). Saves PNG to `output_path`. Closes the figure (no matplotlib backend leaks).
- `eval/src/splunkgate_eval/latency.py` — NEW — `percentiles(latencies_ms: list[float]) → LatencySummary` Pydantic model with `p50, p90, p95, p99, p99_9, mean, count`. `percentile_plot(latencies_ms, output_path) → None` renders a percentile plot (log-scaled x-axis showing the latency tail) and writes PNG.
- `eval/src/splunkgate_eval/cost.py` — NEW — `cost_per_1k_verdicts(baseline_id: str, verdict_count: int) → CostSummary` Pydantic model with `dollars_per_1k: float | None`, `note: str` (e.g., "within Cisco AI Defense 10M/yr free tier" or "TBD pending dev-tier confirmation"). Reads a static `eval/src/splunkgate_eval/_cost_tables.json` for per-baseline rates.
- `eval/src/splunkgate_eval/_cost_tables.json` — NEW — JSON dict mapping baseline IDs to cost records: `{"defenseclaw_regex_only": {"dollars_per_1k": 0.0, "note": "local compute"}, "ai_defense_alone": {"dollars_per_1k": 0.0, "note": "within 10M/yr free tier"}, "splunkgate_full_stack": {"dollars_per_1k": 0.0, "note": "within 10M/yr free tier + Foundation-Sec via | ai"}, "gpt_oss_120b_judge": {"dollars_per_1k": null, "note": "TBD pending Splunk Hosted Models dev-tier confirmation"}, "splunklib_security_regex": {"dollars_per_1k": 0.0, "note": "local compute"}}`.
- `eval/src/splunkgate_eval/report.py` — NEW — `generate_report(results_dir: Path, output_path: Path = Path("docs/eval-results.md")) → None`: reads every `eval/results/<sha>/per_dataset/*.json` produced by `run_full.py`, computes metrics + latency + cost per (evaluator, dataset), renders the headline markdown table per the template in `docs/eval-spec.md` § "The headline table", calls `reliability_diagram` and `percentile_plot` per evaluator into `eval/results/<sha>/reliability/` and `eval/results/<sha>/latency/`, writes the markdown to `output_path`, and emits a summary log line `eval.report.generated path=... rows=... mock_baselines=[...]`. Annotates baselines run in mock mode with `(mock)` next to the row title.
- `eval/scripts/run_full.py` — NEW — orchestrator: iterates `BASELINES × DATASETS` (5 baselines × 5 datasets = 25 cells), calls each baseline against each dataset's loader, collects Verdicts, writes per-dataset JSON to `eval/results/<git-sha>/per_dataset/<dataset>__<baseline>.json` (schema: `{"baseline_id": str, "dataset_id": str, "verdicts": [Verdict.model_dump(), ...], "expected": [{"id": str, "expected_verdict": str, "expected_severity": str}, ...]}`), then calls `report.generate_report(...)`. Reads `--limit N` and `--baselines a,b,c` CLI args. The 5th "baseline" is `splunkgate_full_stack` (SplunkGate's own composition — splunklib_security → AI Defense → Foundation-Sec); story-eval-05 defines it as a thin wrapper that calls `splunkgate_mw.model_middleware` end-to-end. The Splunk-side splunklib.ai 9-regex is the 6th row in the table (per `docs/eval-spec.md` template).
- `eval/scripts/smoke.py` — NEW — runs `run_full.py` with `--limit 25 --baselines defenseclaw_regex_only,ai_defense_alone --datasets benign_control,jailbreakbench` so the smoke set is ~50 prompts × 2 baselines = ~100 verdicts, completing in < 60 seconds. Returns 0 on success, 1 on any unhandled exception. Required by `cicd-06-eval-smoke-job`.
- `eval/tests/test_metrics.py` — NEW — ≥ 10 tests: `precision([1,1,0,0], [1,0,0,0]) == 1.0`; `recall([1,1,0,0], [1,0,0,0]) == 0.5`; `f1` is the harmonic mean; perfect predictions → P=R=F1=1.0; all-wrong → P=R=F1=0.0; `expected_calibration_error([1,0,1,0], [0.9,0.1,0.9,0.1]) ≈ 0.0` (perfectly calibrated); `expected_calibration_error([1,0,1,0], [0.5,0.5,0.5,0.5]) ≈ 0.5` (uncalibrated); ECE is bounded in [0, 1]; `confusion_matrix` returns the documented 2x2 layout.
- `eval/tests/test_latency.py` — NEW — ≥ 6 tests: `percentiles([1,2,3,4,5,6,7,8,9,10]).p50 == 5.5` (or whichever exact stat we pick); `p99` for a 100-item list returns the 99th-percentile value; `count` matches input length; `LatencySummary` validates via Pydantic; `percentile_plot(..., tmp_png).touched()` creates the PNG file; empty input raises `ValueError`.
- `eval/tests/test_report.py` — NEW — ≥ 8 tests: `generate_report` writes a markdown file containing the required column headers (Precision, Recall, F1, ECE, p50 latency, p99 latency, $/1k); the rendered table has at least 5 rows (1 row per baseline + SplunkGate full stack); `(mock)` annotation appears for mock-mode baselines; `Synthetic-Data/pii_leak_corpus/imprompter_payloads.jsonl` content is included via a paper-citation footnote with arxiv:2410.14923; the Anthropic MSJ paper power-law note appears in a footnote; reliability PNGs are written per evaluator; latency PNGs are written per evaluator; running `generate_report` twice on the same input produces identical markdown (deterministic ordering).
- `eval/tests/test_smoke_e2e.py` — NEW — ≥ 4 tests: `python eval/scripts/smoke.py` exits 0 in < 60 seconds; the smoke run produces a `eval/results/<sha>/per_dataset/*.json` artifact; `docs/eval-results.md` is updated (or `eval/results/<sha>/summary.md` is — whichever the report writes by default); a follow-up `generate_report` re-run is idempotent.
- `eval/pyproject.toml` — UPDATE — add `matplotlib` and `numpy` to `[project.optional-dependencies].eval` (these are eval-only — banned from `splunkgate_core`/`splunkgate_judges`).

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the four metric modules
When  `wc -l` is run against each
Then  metrics.py <= 400 LOC
And   reliability.py <= 400 LOC
And   latency.py <= 400 LOC
And   cost.py <= 400 LOC
And   report.py <= 400 LOC

Given the metrics module
When  `uv run python -c "from splunkgate_eval.metrics import precision, recall, f1, expected_calibration_error; print(precision([1,1,0,0],[1,0,0,0]), recall([1,1,0,0],[1,0,0,0]), f1([1,1,0,0],[1,0,0,0]))"` runs
Then  output is "1.0 0.5 0.6666666666666666"

Given a perfectly calibrated probability list
When  expected_calibration_error([1,0,1,0], [0.9,0.1,0.9,0.1]) is computed
Then  the result is approximately 0.0 (within 0.05)

Given the smoke script
When  `python eval/scripts/smoke.py` runs
Then  exit code is 0
And   wall clock is < 60 seconds

Given a smoke run completed
When  `find eval/results -name 'per_dataset' -type d -maxdepth 3 | head -1 | xargs -I{} ls {} | wc -l` runs
Then  >= 2 files are produced (2 baselines × 1 dataset minimum)

Given the report generator
When  `generate_report` is called against the smoke results
Then  `docs/eval-results.md` is written
And   the file contains the substring "Precision"
And   the file contains the substring "Recall"
And   the file contains the substring "F1"
And   the file contains the substring "ECE"
And   the file contains the substring "p50"
And   the file contains the substring "p99"
And   the file contains the substring "$/1k"
And   the file contains the arxiv citation "2410.14923"

Given any baseline run in mock mode
When  the report is rendered
Then  the corresponding row title is suffixed with "(mock)"

Given the metrics + latency tests
When  `uv run pytest eval/tests/test_metrics.py eval/tests/test_latency.py eval/tests/test_report.py eval/tests/test_smoke_e2e.py -v` runs
Then  >= 28 tests pass and 0 fail

Given every modified or new file
When  `uv run mypy --strict eval/src/splunkgate_eval/metrics.py eval/src/splunkgate_eval/reliability.py eval/src/splunkgate_eval/latency.py eval/src/splunkgate_eval/cost.py eval/src/splunkgate_eval/report.py` runs
Then  exit code is 0

Given generate_report runs twice on the same per_dataset JSON inputs
When  the two output markdown files are diffed
Then  diff returns empty (deterministic ordering)
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Metric primitives correct
uv run python - <<'PY'
from splunkgate_eval.metrics import precision, recall, f1, expected_calibration_error
assert precision([1,1,0,0],[1,0,0,0]) == 1.0
assert recall([1,1,0,0],[1,0,0,0]) == 0.5
import math
assert math.isclose(f1([1,1,0,0],[1,0,0,0]), 2/3)
ece_perfect = expected_calibration_error([1,0,1,0], [0.9,0.1,0.9,0.1])
assert ece_perfect < 0.05, f"expected calibrated ECE near 0, got {ece_perfect}"
ece_bad = expected_calibration_error([1,0,1,0], [0.5,0.5,0.5,0.5])
assert ece_bad >= 0.4, f"expected uncalibrated ECE high, got {ece_bad}"
print("OK")
PY

# 2. Smoke script runs in < 60 s
SPLUNKGATE_AI_DEFENSE_MOCK=1 SPLUNKGATE_GPT_OSS_MOCK=1 START=$(date +%s)
SPLUNKGATE_AI_DEFENSE_MOCK=1 SPLUNKGATE_GPT_OSS_MOCK=1 python eval/scripts/smoke.py
END=$(date +%s)
[ $((END - START)) -le 60 ] || { echo "FAIL: smoke took > 60s"; exit 1; }

# 3. Per-dataset JSON artifacts exist
sha_dir=$(ls -td eval/results/*/ 2>/dev/null | head -1)
[ -n "$sha_dir" ] || { echo "FAIL: no results dir"; exit 1; }
[ -d "${sha_dir}per_dataset" ]
n_json=$(find "${sha_dir}per_dataset" -name '*.json' | wc -l)
[ "$n_json" -ge 2 ] || { echo "FAIL: only $n_json per-dataset JSON files"; exit 1; }

# 4. docs/eval-results.md rendered with required columns
test -f docs/eval-results.md
for col in Precision Recall F1 ECE p50 p99 '$/1k' 2410.14923; do
  grep -q "$col" docs/eval-results.md || { echo "FAIL: missing column '$col'"; exit 1; }
done

# 5. Mock annotations present (smoke run uses mock mode)
grep -q '(mock)' docs/eval-results.md || { echo "FAIL: expected (mock) annotation in smoke output"; exit 1; }

# 6. Reliability + latency PNGs exist
[ -d "${sha_dir}reliability" ] && ls "${sha_dir}reliability"/*.png >/dev/null
[ -d "${sha_dir}latency" ] && ls "${sha_dir}latency"/*.png >/dev/null

# 7. Tests pass
uv run pytest eval/tests/test_metrics.py eval/tests/test_latency.py eval/tests/test_report.py eval/tests/test_smoke_e2e.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 28

# 8. Strict typecheck
uv run mypy --strict eval/src/splunkgate_eval/metrics.py eval/src/splunkgate_eval/reliability.py eval/src/splunkgate_eval/latency.py eval/src/splunkgate_eval/cost.py eval/src/splunkgate_eval/report.py

# 9. Determinism — same inputs → same markdown
uv run python -c "from splunkgate_eval.report import generate_report; from pathlib import Path; generate_report(Path('${sha_dir}'), Path('/tmp/eval-1.md'))"
uv run python -c "from splunkgate_eval.report import generate_report; from pathlib import Path; generate_report(Path('${sha_dir}'), Path('/tmp/eval-2.md'))"
diff -q /tmp/eval-1.md /tmp/eval-2.md

# 10. 400-LOC cap
for f in eval/src/splunkgate_eval/metrics.py eval/src/splunkgate_eval/reliability.py eval/src/splunkgate_eval/latency.py eval/src/splunkgate_eval/cost.py eval/src/splunkgate_eval/report.py eval/scripts/run_full.py eval/scripts/smoke.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
echo "ALL CHECKS PASS"
```

---

## Notes for coding agent

- **Per `docs/architecture.md` § "Coding standards" hard rule #1**: every source file ≤ 400 LOC. `metrics.py` could blow this if you put plotting + percentiles + cost + ECE all in one file. **This story is explicitly split into 5 files** (metrics.py / reliability.py / latency.py / cost.py / report.py) to stay within budget. Do not collapse them. If any individual file approaches 350 LOC, factor a helper module out before submitting.
- **Per `docs/eval-spec.md` § "The headline table"**: the table template is verbatim — render its column headers exactly (`Evaluator | Precision | Recall | F1 | ECE | p50 latency | p99 latency | $/1k verdicts`). The 6 default rows are: `splunklib.ai security (9 regex)`, `DefenseClaw regex-only`, `gpt-oss-120b-as-judge`, `Cisco AI Defense alone`, `SplunkGate full stack` (bold), and an optional SplunkGate-with-mock row if `SPLUNKGATE_AI_DEFENSE_MOCK=1`. The smoke run only includes the 2 baselines specified in the smoke script.
- **Per `docs/eval-spec.md` § "Honesty bar"**: every row run in mock mode gets a `(mock)` suffix. The README in `eval/results/<sha>/summary.md` documents this explicitly. Do NOT fabricate numbers when mock mode is on — emit the mock-mode disclaimer as a markdown blockquote above the table.
- **Per `docs/eval-spec.md` § "Honesty bar"** + Imprompter context: the table footnote MUST cite `arxiv:2410.14923` and state Mistral patched 2024-09-13. Render this as a footnote `[^imprompter]` at the bottom of the table. The Anthropic MSJ power-law citation goes in a second footnote `[^msj]` explaining the probabilistic-ceiling caveat.
- **Per `../../../context/01-threat-landscape/02-jailbreak-techniques.md` §5 (Anthropic Many-Shot Jailbreaking PDF grounded)**: the power-law exponent is invariant to SFT/RL — this is the honesty bar for the eval table. The report.py output must include the verbatim caveat (or close paraphrase): "We sit on the same power-law scaling curve as Anthropic showed — this is a probabilistic gate, not a deterministic one."
- **Per `docs/architecture.md` § "Banned"**: numpy / pandas are banned from `splunkgate_core`/`splunkgate_judges`. They are **allowed in `eval/`**. Use numpy for vectorized confusion-matrix / ECE math; use matplotlib for plotting. Do not import either inside `packages/`.
- **ECE formula** (per Naeini et al. 2015, cited in `docs/eval-spec.md`): partition predicted probabilities into `n_bins` equal-width bins; for each bin, compute `|acc(bin) - conf(bin)| * (bin_size / total)`; sum across bins. With `n_bins=10` and equal-width bins, edge case: empty bin contributes 0. Validate against sklearn or a hand-rolled reference if drift suspected. Pass threshold per the spec is `ECE ≤ 0.05`.
- **The `splunkgate_full_stack` "baseline"**: not technically a baseline, but the headline row. Wires `splunklib.ai.security.detect_injection` → `splunkgate_judges.ai_defense.AIDefenseClient` → `splunkgate_judges.foundation_sec.FoundationSecClient`. Wraps these in a single callable matching the `EvalPrompt → Verdict` signature. Imports from `splunkgate_mw.model_middleware` to reuse the production composition path (per EPIC-06 story-mw-03 / story-mw-04). If `splunkgate_mw` is not yet implemented when this story runs, gate the row behind `--baselines` CLI arg and skip it in the smoke set.
- **Per `docs/eval-spec.md` § "Eval harness layout"**: the output directory shape is `eval/results/<git-sha>/{summary.md, per_dataset/, reliability/, latency/, cost.json, versus_baselines.md}`. `report.py` writes `summary.md` (the headline) and also copies it to `docs/eval-results.md` so the README's eval table is the most recent run. The `eval.yml` CI workflow commits `docs/eval-results.md` on main.
- **Git SHA detection**: `subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()` — fallback to `"local"` if git is unavailable (e.g., shallow CI checkout).
- **Smoke set sizing**: at `--limit 25` × 2 baselines × 2 datasets = 100 verdicts. With `SPLUNKGATE_AI_DEFENSE_MOCK=1` and `SPLUNKGATE_GPT_OSS_MOCK=1`, this is pure in-process Python — expected wall clock ~5–10 seconds. The 60-second cap exists to catch performance regressions in the metrics/reliability/cost path. CI runs this on every PR per story-cicd-06-eval-smoke-job.
- **matplotlib backend**: use `matplotlib.use("Agg")` before importing pyplot so the report runs headless in CI without a display server.
- **Deterministic ordering** in report.py: iterate baselines and datasets in alphabetical order; iterate verdict records in `id` order; sort per-bin reliability data by bin midpoint. Two runs over the same inputs must produce byte-identical markdown.
- Estimate breakdown: ~30 min metrics + ECE + tests, ~20 min latency + plot + tests, ~10 min cost table, ~30 min report.py rendering + footnotes, ~20 min run_full + smoke + e2e tests, ~10 min strict mypy + LOC trim across all 5 files.

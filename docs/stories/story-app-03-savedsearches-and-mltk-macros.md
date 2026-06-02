# Story — Saved searches + 8 MLTK macros (DNS Guard 1st-place pattern)

**ID:** story-app-03-savedsearches-and-mltk-macros
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-02-props-transforms-for-aegis-verdict-sourcetype
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Splunk app evaluator (judge or AppInspect) reviewing the Aegis app's ML pattern
**I want to** see 8 MLTK macros using `fit DensityFunction`, `fit KMeans k=2`, and `anomalydetection` for verdict-trend forecasting + verdict-cluster behavioral analysis, plus saved searches that drive each dashboard panel
**So that** Aegis mirrors the proven 1st-place DNS Guard AI 2025 winning shape — pure SPL + MLTK, zero Python in the app dir, zero LLM — and judges immediately recognize the "Splunk-native ML done right" pattern that took the AI/ML track last year

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/default/macros.conf` — NEW — 8 SPL macros total, grouped by concern. Utility macros: `[aegis_data]` (canonical search base — `search sourcetype=cisco_ai_defense:aegis_verdict`), `[aegis_extract_rule]` (mvexpand rule field for per-rule analysis), `[update_verdict_history]` (`outputlookup append=true verdict_history_lookup` — feeds story-app-04's KV-store). ML macros (5): `[setup_verdict_trend_forecast]` (`fit DensityFunction verdict_count by "agent_id" dist=norm threshold=0.01 into aegis_verdict_trend_model`), `[train_verdict_trend_forecast]` (incremental `partial_fit=true` retrain), `[ad_verdict_burst_detection]` (`anomalydetection action=annotate` on per-agent verdict-rate windows), `[setup_agent_behavioral_clustering]` (`fit KMeans avg_latency_ms verdict_rate_per_hour block_ratio severity_score_avg k=2 into aegis_agent_behavior_clusters`), `[train_agent_behavioral_clustering]` (incremental `partial_fit=true` retrain). Mirrors DNS Guard's `macros.conf` shape verbatim — same 8-macro count, same `fit DensityFunction`+`fit KMeans k=2`+`anomalydetection` triad.
- `splunk_apps/aegis_app/default/savedsearches.conf` — NEW — saved searches that drive dashboards + ES integration. At minimum: `[Aegis - All Verdicts 24h]` (`search = `aegis_data` earliest=-24h | stats count by verdict_label`), `[Aegis - HIGH severity by agent]` (`search = `aegis_data` severity=HIGH earliest=-24h | stats count by agent_id | sort -count`), `[Aegis - MSJ scaling indicator]` (`search = `aegis_data` earliest=-7d | stats count(eval(severity!="NONE_SEVERITY")) as detections count as total_msgs by agent_id | eval detection_rate = round(detections/total_msgs, 4) | sort -total_msgs`). Plus the setup/train/AD scheduled searches that invoke each ML macro (6 of them, cron `15 */6 * * *` for the periodic retrains, matching DNS Guard). All ML training searches disabled by default (`disabled = 1`); user enables them after MLTK app is installed. Aegis-global notable-event correlation search (`[Aegis - HIGH severity correlation alert]`) generates ES notable events via `action.risk = 1, action.notable = 1`.
- `splunk_apps/aegis_app/default/data/ui/views/aegis_setup.xml` — NEW — minimal Splunk classic-XML setup dashboard with "Enable ML training" button that toggles the `disabled = 0` flag on the 6 training searches via the Splunk REST API (no Python — uses standard Splunk classic-XML form actions). Mirrors DNS Guard's `dns_guard_ai_-_setup.xml`.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/default/macros.conf exists
When  grep -cE "^\[(aegis_data|aegis_extract_rule|update_verdict_history|setup_verdict_trend_forecast|train_verdict_trend_forecast|ad_verdict_burst_detection|setup_agent_behavioral_clustering|train_agent_behavioral_clustering)\]$" runs
Then  count == 8 (exactly 8 macros, matching DNS Guard's 8-macro count)

Given macros.conf is parsed
When  grep -cE "fit DensityFunction|fit KMeans .* k=2|anomalydetection" runs
Then  count >= 4 (DensityFunction setup + train, KMeans setup + train, anomalydetection — all three MLTK primitives present)

Given macros.conf contains the [setup_verdict_trend_forecast] stanza
When  grep "definition = " on that stanza runs
Then  the value contains "fit DensityFunction" AND "dist=norm" AND "into aegis_verdict_trend_model"

Given macros.conf contains the [setup_agent_behavioral_clustering] stanza
When  grep "definition = " on that stanza runs
Then  the value contains "fit KMeans" AND "k=2" AND "into aegis_agent_behavior_clusters"

Given macros.conf contains the [ad_verdict_burst_detection] stanza
When  grep "definition = " runs
Then  the value contains "anomalydetection" AND "action=annotate"

Given splunk_apps/aegis_app/default/savedsearches.conf exists
When  grep -cE "^\[Aegis - " runs
Then  count >= 9 (3 dashboard-driving searches + 6 ML-pipeline searches)

Given savedsearches.conf is parsed
When  grep -cE "^cron_schedule = 15 \*/6 \* \* \*$" runs
Then  count >= 5 (5 of the 6 periodic ML training searches; correlation alert may use different cron)

Given savedsearches.conf is parsed
When  grep -c "^disabled = 1$" runs
Then  count >= 6 (all 6 ML training searches disabled by default — user opts in)

Given the [Aegis - HIGH severity correlation alert] stanza
When  grep "action.risk = 1\|action.notable = 1" runs
Then  both lines present (feeds ES RBA in story app-08)

Given the [Aegis - MSJ scaling indicator] stanza
When  grep "definition = \|search = " runs
Then  the search contains "stats count" AND "by agent_id" AND "detection_rate"

Given a Splunk container with MLTK installed and synthetic verdict events loaded
When  the saved search "Aegis - Setup Model - Verdict Trend Forecast" runs once manually
Then  exit code is 0 AND the model "aegis_verdict_trend_model" appears in `| summary aegis_verdict_trend_model`

Given splunk-appinspect runs against splunk_apps/aegis_app/
When  the output is parsed
Then  zero "error"-severity findings against tags savedsearches_conf_valid, macros_conf_valid
```

---

## Shell verification

```bash
set -euo pipefail

# 1. Files exist
test -f splunk_apps/aegis_app/default/macros.conf
test -f splunk_apps/aegis_app/default/savedsearches.conf
test -f splunk_apps/aegis_app/default/data/ui/views/aegis_setup.xml

# 2. Exactly 8 macros (the DNS Guard pattern count)
test "$(grep -cE '^\[(aegis_data|aegis_extract_rule|update_verdict_history|setup_verdict_trend_forecast|train_verdict_trend_forecast|ad_verdict_burst_detection|setup_agent_behavioral_clustering|train_agent_behavioral_clustering)\]$' splunk_apps/aegis_app/default/macros.conf)" -eq 8

# 3. All three MLTK primitives used in macros
grep -q 'fit DensityFunction' splunk_apps/aegis_app/default/macros.conf
grep -q 'fit KMeans' splunk_apps/aegis_app/default/macros.conf
grep -q 'k=2' splunk_apps/aegis_app/default/macros.conf
grep -q 'anomalydetection' splunk_apps/aegis_app/default/macros.conf
grep -q 'action=annotate' splunk_apps/aegis_app/default/macros.conf
grep -q 'dist=norm' splunk_apps/aegis_app/default/macros.conf
grep -q 'into aegis_verdict_trend_model' splunk_apps/aegis_app/default/macros.conf
grep -q 'into aegis_agent_behavior_clusters' splunk_apps/aegis_app/default/macros.conf

# 4. Savedsearches has dashboard-driving searches + ML training + correlation alert
test "$(grep -cE '^\[Aegis - ' splunk_apps/aegis_app/default/savedsearches.conf)" -ge 9
grep -q '^\[Aegis - All Verdicts 24h\]$' splunk_apps/aegis_app/default/savedsearches.conf
grep -q '^\[Aegis - HIGH severity by agent\]$' splunk_apps/aegis_app/default/savedsearches.conf
grep -q '^\[Aegis - MSJ scaling indicator\]$' splunk_apps/aegis_app/default/savedsearches.conf
grep -q '^\[Aegis - HIGH severity correlation alert\]$' splunk_apps/aegis_app/default/savedsearches.conf

# 5. ML training searches disabled by default
test "$(grep -c '^disabled = 1$' splunk_apps/aegis_app/default/savedsearches.conf)" -ge 6

# 6. Periodic cron schedule matches DNS Guard pattern (every 6 hours)
test "$(grep -cE '^cron_schedule = 15 \*/6 \* \* \*$' splunk_apps/aegis_app/default/savedsearches.conf)" -ge 5

# 7. Correlation alert wired to ES risk + notable
awk '/^\[Aegis - HIGH severity correlation alert\]/,/^\[/' splunk_apps/aegis_app/default/savedsearches.conf | grep -q 'action.risk = 1'
awk '/^\[Aegis - HIGH severity correlation alert\]/,/^\[/' splunk_apps/aegis_app/default/savedsearches.conf | grep -q 'action.notable = 1'

# 8. Setup XML well-formed
python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/aegis_app/default/data/ui/views/aegis_setup.xml')"

# 9. Live SPL syntax check (gated on AEGIS_SPLUNK_HEC_TOKEN)
if [ -n "${AEGIS_SPLUNK_API_TOKEN:-}" ]; then
  uv run python - <<'PY'
import splunklib.client as c
svc = c.connect(host="${AEGIS_SPLUNK_HOST}", token="${AEGIS_SPLUNK_API_TOKEN}", app="aegis_app")
# Parse-only: validates SPL without running
for name in ["Aegis - All Verdicts 24h", "Aegis - MSJ scaling indicator", "Aegis - HIGH severity by agent"]:
    s = svc.saved_searches[name]
    job = svc.parse(s["search"])
    assert job["status"]["http_status"] == "200", f"Parse failed for {name}"
print("All saved-search SPL parses OK")
PY
fi

# 10. AppInspect
uv run splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud \
  --output-file appinspect-report.json --data-format json
python - <<'PY'
import json, sys
r = json.load(open("appinspect-report.json"))
errors = [c for rep in r.get("reports", []) for g in rep.get("groups", []) for c in g.get("checks", []) if c.get("result") == "error"]
if errors:
    for e in errors: print(" -", e.get("name"), e.get("messages"))
    sys.exit(1)
PY

# 11. 400-LOC sanity
test "$(wc -l < splunk_apps/aegis_app/default/macros.conf)" -le 400
test "$(wc -l < splunk_apps/aegis_app/default/savedsearches.conf)" -le 400
test "$(wc -l < splunk_apps/aegis_app/default/data/ui/views/aegis_setup.xml)" -le 400
```

All eleven blocks must exit 0 before opening the PR (block 9 gated on env var, otherwise skipped).

---

## Notes for coding agent

- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard AI (1st place AI/ML 2025) used pure SPL + MLTK + 8 macros, no Python, no LLM. The exact macro count (8) and the triad of `fit DensityFunction` + `fit KMeans k=2` + `anomalydetection` is what the judges rewarded. Aegis mirrors this verbatim with the threat domain swapped from DNS-anomaly to agent-verdict.
- Per `../../../context/05-splunk-core/05-spl-reference.md`, `fit DensityFunction <field> by "<groupby>" dist=norm threshold=0.01 into <model>` is the canonical Splunk MLTK pattern for univariate density anomaly detection. `fit KMeans <fields> k=2 into <model>` is the canonical clustering pattern (k=2 = "normal vs anomalous" two-cluster split). `anomalydetection <fields> action=annotate` is the built-in statistical AD command.
- Per `../../../context/05-splunk-core/10-mltk-machine-learning-toolkit.md`, MLTK is a separate Splunk app dependency. Document in `splunk_apps/aegis_app/README` (story app-01) that MLTK 5.x or later must be installed for the ML pipelines to run. The training saved searches are disabled by default so the app installs cleanly even without MLTK; user enables after MLTK is present.
- The 5 ML macros split as: 2 setup (cold-start one-shot — DensityFunction + KMeans) + 2 train (incremental `partial_fit=true` — DensityFunction + KMeans) + 1 anomalydetection (live — no fit needed). Plus 3 utility macros = 8 total, matching DNS Guard.
- DNS Guard's `partial_fit=true` pattern (incremental retraining) keeps models fresh without full retrains. Replicate verbatim in `[train_verdict_trend_forecast]` and `[train_agent_behavioral_clustering]`.
- The 4 features for KMeans agent clustering are: `avg_latency_ms` (compute latency), `verdict_rate_per_hour` (volume), `block_ratio` (BLOCK count / total count), `severity_score_avg` (the EVAL'd severity_score from story-app-02 props.conf). These split agents into "safe" vs "high-risk" clusters with k=2.
- Per `../../../context/01-threat-landscape/02-jailbreak-techniques.md`, Anthropic's Many-Shot Jailbreaking (MSJ) finding shows detection rate degrades as context length grows. The `[Aegis - MSJ scaling indicator]` saved search exposes this as `detection_rate = detections / total_msgs` per agent over 7 days — drives the small chart in dashboard 1 (story app-05) and keeps the dashboard honest about the probabilistic ceiling.
- The `[Aegis - HIGH severity correlation alert]` stanza wires ES RBA via `action.risk = 1` and `action.notable = 1`. Story app-08 (risk_factors.conf) defines what those risks map to. This story creates the alert; story app-08 defines the risk factors it feeds.
- `cron_schedule = 15 */6 * * *` (DNS Guard's exact cron) runs every 6 hours at minute 15 — avoids the top-of-hour stampede that hits Splunk Cloud's saved-search scheduler quotas.
- Do NOT use `index=*` or `index=main` in macro definitions; the dashboards set the index via `<token>` substitution. Hardcoding the index kills multi-tenant deployments and is an AppInspect warning.
- The `aegis_setup.xml` form-action approach (toggle `disabled` via REST POST) mirrors DNS Guard's setup dashboard — no Python in the app dir. Splunk's classic-XML `<form>` + `<query>` blocks with `target="rest:..."` is the no-bin/ pattern for admin UI.
- If macros.conf approaches 400 LOC due to long multi-line macro `definition = ...\` lines, consolidate ML feature lists onto single lines — DNS Guard's KMeans macro fits on ~3 lines with backslash continuation, no need to expand further.
- Do NOT replicate DNS Guard's `dns_data` macro using `datamodel Network_Resolution` — Aegis has no equivalent CIM datamodel for verdicts (yet). The `[aegis_data]` macro is a flat `search sourcetype=cisco_ai_defense:aegis_verdict` instead. Note in macro description that a future story could add an `aegis_verdict` CIM datamodel.

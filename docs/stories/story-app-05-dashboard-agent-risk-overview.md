# Story — Dashboard 1: Agent Risk Overview (Dashboard Studio v2)

**ID:** story-app-05-dashboard-agent-risk-overview
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-03-savedsearches-and-mltk-macros
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** CISO opening Splunk in the morning
**I want to** glance at the "Agent Risk Overview" dashboard and answer "are my agents safe today?" in under 5 seconds — 4 KPI tiles up top, stacked time-series of verdicts by label, heatmap of rules-by-hour, top-agents-by-BLOCK table, and a small MSJ scaling indicator
**So that** I have an at-a-glance trust signal before my SOC team's stand-up, and I can drill down into the Verdict Inspector (story app-06) by clicking any panel

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml` — NEW — Dashboard Studio v2 dashboard in JSON-in-XML format. Wrapper: `<dashboard version="2.0" theme="dark"><label>Aegis — Agent Risk Overview</label><description>Real-time CISO view of AI agent safety verdicts. Aegis events land in the same cisco_ai_defense:* sourcetype family as the Cisco Security Cloud add-on (Splunkbase 7404).</description><definition><![CDATA[ {JSON} ]]></definition></dashboard>`. The CDATA JSON declares: 4 KPI single-value visualizations (`kpi_total_verdicts`, `kpi_block_verdicts`, `kpi_high_severity`, `kpi_distinct_agents`), 1 line chart with stacked verdicts (`ts_verdicts_24h`), 1 heatmap (`heatmap_rules_by_hour`), 1 table (`table_top_agents`), 1 small MSJ scaling line chart (`msj_scaling_chart`); 8 dataSources (one per viz), each `type: "ds.search"` using `aegis_data` macro + per-panel `| stats`/`| timechart`; 1 timerange input (`input_time`); layout block uses absolute positioning per Dashboard Studio v2 grid (12-column, panels sized 3/6/12 wide depending on KPI vs main vs full-width). All drill-downs point at `verdict_inspector` with URL params (`form.time.earliest=...&form.rule=...&form.agent_id=...`). File total: target ≤ 380 LOC; if approaching 400, split panel JSON into a 2nd view file via Splunk view-include (`<view ref="agent_risk_overview_panels">`).
- `splunk_apps/aegis_app/default/data/ui/nav/default.xml` — UPDATE — confirm `<view name="agent_risk_overview" default="true" />` is set as the default view (this is the landing dashboard).

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml exists
When  python -c "import xml.etree.ElementTree as ET; ET.parse(...)" runs
Then  exit code is 0 (well-formed XML)

Given the XML file is parsed
When  grep -E '^<dashboard version="2.0"' runs
Then  exactly one match (Dashboard Studio v2 declared)

Given the XML file is parsed
When  grep 'theme="dark"' runs
Then  exactly one match (dark theme per DNS Guard 1st-place pattern)

Given the CDATA JSON is extracted from the XML
When  python -c "import xml.etree.ElementTree as ET, json; root = ET.parse('agent_risk_overview.xml').getroot(); d = root.find('definition').text; json.loads(d)" runs
Then  exit code is 0 (CDATA JSON parses cleanly)

Given the parsed JSON
When  python -c "j = json.load(...); print(len(j['visualizations']))" runs
Then  output is exactly 8 (4 KPIs + ts + heatmap + table + msj)

Given the parsed JSON
When  the visualizations keys are inspected
Then  the set contains exactly: kpi_total_verdicts, kpi_block_verdicts, kpi_high_severity, kpi_distinct_agents, ts_verdicts_24h, heatmap_rules_by_hour, table_top_agents, msj_scaling_chart

Given the parsed JSON
When  python -c "j = json.load(...); print(len(j['dataSources']))" runs
Then  output is exactly 8 (one dataSource per visualization)

Given each dataSource SPL query
When  grep -c "sourcetype=cisco_ai_defense:aegis_verdict\|`aegis_data`" across all dataSources runs
Then  count == 8 (every panel uses the canonical sourcetype or macro)

Given the parsed JSON
When  the drilldown configs on heatmap_rules_by_hour and ts_verdicts_24h are inspected
Then  both contain "url" or "link" pointing to "verdict_inspector"

Given the parsed JSON
When  the panel msj_scaling_chart description is inspected
Then  it contains "MSJ" or "Many-Shot Jailbreaking" (honest about the probabilistic ceiling)

Given the XML file
When  wc -l runs
Then  output is <= 400 (LOC cap per docs/architecture.md ADR-009)

Given a Splunk Cloud instance with the app installed and synthetic verdict events loaded
When  the dashboard is loaded via Playwright at /en-US/app/aegis_app/agent_risk_overview
Then  the 4 KPI tiles render numeric values within 3s
And   the heatmap shows ≥ 1 cell with severity-weighted color within 5s
And   browser console errors == 0

Given splunk-appinspect runs against splunk_apps/aegis_app/
When  the output is parsed
Then  zero "error"-severity findings against tags dashboard_studio_v2_valid, simple_xml_valid_views
```

---

## Shell verification

```bash
set -euo pipefail

# 1. File exists and is well-formed XML
test -f splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml
python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml')"

# 2. Dashboard Studio v2 + dark theme declared
grep -q '<dashboard version="2.0"' splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml
grep -q 'theme="dark"' splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml
grep -q '<label>Aegis — Agent Risk Overview</label>' splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml

# 3. CDATA JSON parses
python - <<'PY'
import xml.etree.ElementTree as ET, json, sys
root = ET.parse("splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml").getroot()
defn = root.find(".//definition")
j = json.loads(defn.text)

# 4. Exactly 8 visualizations + 8 dataSources with the right names
expected_viz = {"kpi_total_verdicts","kpi_block_verdicts","kpi_high_severity","kpi_distinct_agents",
                "ts_verdicts_24h","heatmap_rules_by_hour","table_top_agents","msj_scaling_chart"}
assert set(j["visualizations"].keys()) == expected_viz, f"Viz mismatch: {set(j['visualizations'].keys())}"
assert len(j["dataSources"]) == 8, f"Expected 8 dataSources, got {len(j['dataSources'])}"

# 5. Every dataSource references our sourcetype or macro
for name, ds in j["dataSources"].items():
    q = ds.get("options",{}).get("query","")
    assert "cisco_ai_defense:aegis_verdict" in q or "`aegis_data`" in q, f"{name} missing sourcetype: {q}"

# 6. Time-range input present
assert "input_time" in j.get("inputs",{}), "input_time missing"
assert j["inputs"]["input_time"]["type"] == "input.timerange", "timerange input wrong type"

# 7. Drilldowns wired to verdict_inspector
drilldowns_str = json.dumps(j)
assert "verdict_inspector" in drilldowns_str, "no drill-down to verdict_inspector found"

# 8. MSJ panel honestly references the finding
msj = j["visualizations"]["msj_scaling_chart"]
desc = (msj.get("description") or "") + (msj.get("title") or "")
assert "MSJ" in desc or "Many-Shot" in desc or "many-shot" in desc.lower(), \
    "MSJ panel missing Many-Shot Jailbreaking attribution"
print("All structural checks passed.")
PY

# 9. LOC cap
test "$(wc -l < splunk_apps/aegis_app/default/data/ui/views/agent_risk_overview.xml)" -le 400

# 10. Playwright visual smoke (gated on AEGIS_SPLUNK_HOST)
if [ -n "${AEGIS_SPLUNK_HOST:-}" ]; then
  uv run playwright install --with-deps chromium >/dev/null 2>&1 || true
  uv run python - <<'PY'
from playwright.sync_api import sync_playwright
import os, sys
url = f"https://{os.environ['AEGIS_SPLUNK_HOST']}:8000/en-US/app/aegis_app/agent_risk_overview"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(ignore_https_errors=True); page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-test="visualization"]', timeout=15000)
    page.screenshot(path="screenshots/current/agent_risk_overview--desktop.png", full_page=True)
    assert not errors, f"console errors: {errors}"
    b.close()
PY
fi

# 11. AppInspect
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
```

All eleven blocks must exit 0 before opening the PR (block 10 gated on env var).

---

## Notes for coding agent

- Per `docs/ux-spec.md` § "Dashboard 1 — Agent Risk Overview", the exact 5-section layout is: 4-KPI top strip, time-series verdicts-stacked-by-label, heatmap rules-by-hour, top-agents-by-BLOCK table, MSJ scaling indicator. Do not add or drop sections without re-reading the ux-spec.
- Per `docs/architecture.md` § "ADR-008", we use Dashboard Studio v2 (JSON-in-XML) wrapped in the Classic Simple XML `<dashboard>` shell. The shell looks like: `<dashboard version="2.0" theme="dark"><label>...</label><description>...</description><definition><![CDATA[ {json} ]]></definition></dashboard>`. Anything outside the CDATA stays as XML; everything inside is Dashboard Studio v2 JSON spec.
- Per `../../../context/05-splunk-core/07-dashboard-studio-v2.md`, Dashboard Studio v2's JSON spec requires top-level keys: `title`, `visualizations` (dict of named viz configs), `dataSources` (dict of named query configs), `inputs`, `defaults`, `layout`. Each visualization references `dataSources` by ID. Each `ds.search` dataSource has `options.query` (the SPL) and `options.earliestTime` / `options.latestTime` (token-bound to the timerange input).
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, DNS Guard 1st-place winner used `theme="dark"` — judge pool rewarded the dark-mode Splunk-native look. Do not override to `theme="light"`.
- Per `docs/ux-spec.md` § "Design tokens", do NOT add custom CSS, custom fonts, or `rounded-xl`-style styling. Splunk's design tokens handle color + spacing. Custom overrides defeat the Splunk-native winning pattern.
- The 11 Cisco AI Defense rule names for the heatmap Y-axis come verbatim from `../../../context/07-cisco-stack/01-ai-defense-deep.md`: Prompt Injection, Code Detection, PII, PHI, PCI, Toxicity, Profanity, Harassment, Hate Speech, Violence, Self-Harm. The heatmap query is approximately: `` `aegis_data` earliest=-24h | mvexpand rule | bin _time span=1h | stats sum(severity_score) as score by _time, rule ``.
- The MSJ scaling panel must cite `../../../context/01-threat-landscape/02-jailbreak-techniques.md` in its `description` field — exact quote: "Detection rate degrades as in-context message count grows (Anthropic 2024). Aegis shows the live floor — be honest about the probabilistic ceiling." This is the credibility move per ux-spec.md.
- Drill-down URL pattern for Dashboard Studio v2: `{"type":"link.url","url":"/app/aegis_app/verdict_inspector?form.time.earliest=$row._time$&form.rule=$row.rule$"}`. Token substitution uses `$row.<field>$` for table rows and `$click.value$` for heatmap cells per Dashboard Studio v2 docs.
- 12-column grid layout with absolute positioning: KPIs at `y:0, h:120, w:3` each (x: 0/3/6/9 for the 4 tiles in a row), time-series at `y:120, h:280, w:12`, heatmap at `y:400, h:320, w:8`, top-agents table at `y:400, h:320, w:4`, MSJ chart at `y:720, h:200, w:4`. Adjust dimensions if any panel feels cramped during Playwright visual review (story app-10).
- If the JSON-in-XML file approaches 400 LOC, split visualization JSON into a sibling file `agent_risk_overview_panels.xml` referenced via `<view ref="agent_risk_overview_panels" />` per Splunk Classic Simple XML view-include docs. Splunk Dashboard Studio v2 does not natively support JSON includes — the include happens at the XML wrapper layer, with the JSON spread across two `<definition>` blocks loaded sequentially. If this is too clunky, simplify by reducing per-panel SPL complexity (use `tstats` instead of `stats` for top-N panels, drops ~30 LOC).
- The Playwright smoke test in shell block 10 generates `screenshots/current/agent_risk_overview--desktop.png` — story app-10 owns the anchor diff against `screenshots/anchor/agent_risk_overview--desktop.png`. This story just generates the current screenshot if env vars permit; the anchor comparison gates the PR in app-10.
- Do NOT inline panel SPL with hardcoded `index=main` — use the `aegis_data` macro so it inherits the index from the macro definition (story app-03). Hardcoding fails multi-tenant deployments and AppInspect.
- Theme color for severity: re-use the design token palette from ux-spec.md (`#5CB85C` NONE, `#F0AD4E` LOW, `#FF9900` MEDIUM, `#D9534F` HIGH). Dashboard Studio v2 supports `colorPalette` per visualization — wire it on the time-series and heatmap.

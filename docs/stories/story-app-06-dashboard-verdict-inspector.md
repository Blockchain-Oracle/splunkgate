# Story — Dashboard 2: Verdict Inspector (Dashboard Studio v2)

**ID:** story-app-06-dashboard-verdict-inspector
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-03-savedsearches-and-mltk-macros, story-app-04-collections-conf-kvstore-verdict-history
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** SOC analyst investigating a specific Aegis verdict
**I want to** land on the Verdict Inspector from any drill-down (Dashboard 1 heatmap cell, ES notable, or direct URL), see the matching verdicts as a sortable table, click a row to slide in a full detail panel (input text, full evaluator chain, rules with confidence, Foundation-Sec explanation, OTel trace_id, "Open in Splunk ES" button), and view related events from the same trace_id across all four surfaces
**So that** I can move from "this verdict tripped" to "here's the full agent session context" in one click without context-switching between Splunk Search, ES Investigation, and external tools

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml` — NEW — Dashboard Studio v2 dashboard. Wrapper: `<dashboard version="2.0" theme="dark"><label>Aegis — Verdict Inspector</label><description>SOC + AI platform engineer drill-down. Slide-in detail panel + related-events trace view. Sourced from cisco_ai_defense:aegis_verdict + aegis_verdict_history KV-store.</description><definition><![CDATA[ {JSON} ]]></definition></dashboard>`. JSON declares: 5 inputs (`input_time` timerange, `input_agent_id` dropdown — populated by `| stats values(agent_id)`, `input_rule` dropdown — populated by `| mvexpand rule | stats values(rule)`, `input_severity` dropdown — fixed values, `input_verdict_label` dropdown — fixed values). 4 visualizations: `verdict_filter_bar` (markdown showing active filters), `verdict_table` (the main table — columns timestamp/agent_id/surface/verdict_label/severity/rules/explanation_truncated/latency_ms/trace_id, click → opens detail panel via drilldown action), `detail_panel` (slide-in single-event viz showing full Verdict object, only renders when `$row.trace_id$` token is set), `related_events_panel` (related events from same trace_id across all four surfaces, columns timestamp/surface/verdict_label/severity). 4 dataSources (one per non-input viz), all using `aegis_data` macro + per-panel filters bound to inputs via `$input_*$` tokens. Layout: filter bar at top (full width), verdict_table (12-wide, h:400) below filters, detail_panel (8-wide, h:600, conditionally visible) + related_events_panel (4-wide, h:600) below table. Drill-down on detail_panel includes an "Open in Splunk ES" link (`/app/SplunkEnterpriseSecuritySuite/investigation_workbench?form.trace_id=$row.trace_id$`). File total: target ≤ 380 LOC.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml exists
When  python -c "import xml.etree.ElementTree as ET; ET.parse(...)" runs
Then  exit code is 0 (well-formed XML)

Given the XML file is parsed
When  grep -E '^<dashboard version="2.0"' runs
Then  exactly one match (Dashboard Studio v2 declared)

Given the XML file is parsed
When  grep 'theme="dark"' runs
Then  exactly one match (dark theme)

Given the CDATA JSON is extracted
When  json.loads(definition.text) runs
Then  exit code is 0 (JSON parses)

Given the parsed JSON
When  python -c "print(set(j['inputs'].keys()))" runs
Then  the set is exactly {"input_time","input_agent_id","input_rule","input_severity","input_verdict_label"}

Given the parsed JSON
When  python -c "print(set(j['visualizations'].keys()))" runs
Then  the set is exactly {"verdict_filter_bar","verdict_table","detail_panel","related_events_panel"}

Given the parsed JSON dataSources
When  each query string is inspected
Then  every query contains "`aegis_data`" or "sourcetype=cisco_ai_defense:aegis_verdict"

Given the parsed JSON visualizations.verdict_table
When  its drilldown config is inspected
Then  it contains a click handler that sets a token (e.g., "tokens" array with "name":"row_trace_id") OR opens detail_panel

Given the parsed JSON visualizations.detail_panel
When  its drilldown config is inspected
Then  it contains a link to "/app/SplunkEnterpriseSecuritySuite/" (Open in ES button)

Given the parsed JSON visualizations.related_events_panel
When  its dataSource query is inspected
Then  the query contains "trace_id" filter bound to "$row_trace_id$" or equivalent token

Given the XML file
When  wc -l runs
Then  output <= 400

Given URL params are passed as ?form.time.earliest=-1h&form.rule=PII (deep-link pattern from Dashboard 1)
When  the dashboard loads
Then  the input_time and input_rule values reflect the URL params (Splunk Dashboard Studio v2 default URL-binding)

Given a Splunk Cloud instance with the app installed and synthetic events loaded
When  the dashboard loads via Playwright at /en-US/app/aegis_app/verdict_inspector
Then  the verdict_table renders ≥ 1 row within 5s
And   clicking a row sets the row_trace_id token and the detail_panel becomes visible within 1s
And   browser console errors == 0

Given splunk-appinspect runs against splunk_apps/aegis_app/
When  the output is parsed
Then  zero "error"-severity findings against tags dashboard_studio_v2_valid, simple_xml_valid_views
```

---

## Shell verification

```bash
set -euo pipefail

# 1. File exists, XML well-formed
test -f splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml
python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml')"

# 2. Dashboard Studio v2 + dark theme
grep -q '<dashboard version="2.0"' splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml
grep -q 'theme="dark"' splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml
grep -q '<label>Aegis — Verdict Inspector</label>' splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml

# 3. JSON structural checks
python - <<'PY'
import xml.etree.ElementTree as ET, json, sys
root = ET.parse("splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml").getroot()
defn = root.find(".//definition")
j = json.loads(defn.text)

expected_inputs = {"input_time","input_agent_id","input_rule","input_severity","input_verdict_label"}
assert set(j["inputs"].keys()) == expected_inputs, f"Inputs mismatch: {set(j['inputs'].keys())}"

expected_viz = {"verdict_filter_bar","verdict_table","detail_panel","related_events_panel"}
assert set(j["visualizations"].keys()) == expected_viz, f"Viz mismatch: {set(j['visualizations'].keys())}"

# Every dataSource references our sourcetype/macro
for name, ds in j["dataSources"].items():
    q = ds.get("options",{}).get("query","")
    assert "cisco_ai_defense:aegis_verdict" in q or "`aegis_data`" in q, f"{name} missing canonical search: {q}"

# Drilldown on verdict_table -> detail_panel via token
table = j["visualizations"]["verdict_table"]
drill_str = json.dumps(table)
assert "trace_id" in drill_str.lower(), "verdict_table drilldown missing trace_id token wiring"

# Detail panel -> Open in ES link
detail = j["visualizations"]["detail_panel"]
detail_str = json.dumps(detail)
assert "SplunkEnterpriseSecuritySuite" in detail_str, "detail_panel missing Open-in-ES link"

# Related events SPL uses trace_id token
rel = j["dataSources"][[k for k,ds in j["dataSources"].items() if "related" in k.lower()][0]]
assert "trace_id" in rel["options"]["query"], "related-events SPL must filter by trace_id"
print("All structural checks passed.")
PY

# 4. LOC cap
test "$(wc -l < splunk_apps/aegis_app/default/data/ui/views/verdict_inspector.xml)" -le 400

# 5. Playwright deep-link test (gated on AEGIS_SPLUNK_HOST)
if [ -n "${AEGIS_SPLUNK_HOST:-}" ]; then
  uv run python - <<'PY'
from playwright.sync_api import sync_playwright
import os
base = f"https://{os.environ['AEGIS_SPLUNK_HOST']}:8000/en-US/app/aegis_app/verdict_inspector"
url = f"{base}?form.time.earliest=-24h&form.rule=PII"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(ignore_https_errors=True); page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-test="visualization"]', timeout=15000)
    # Click first table row -> detail panel should appear
    rows = page.locator('[data-test-id="verdict_table"] tr[role="row"]')
    if rows.count() > 0:
        rows.first.click()
        page.wait_for_selector('[data-test-id="detail_panel"]', timeout=5000)
    page.screenshot(path="screenshots/current/verdict_inspector--desktop.png", full_page=True)
    assert not errors, f"console errors: {errors}"
    b.close()
PY
fi

# 6. AppInspect
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

All six blocks must exit 0 before opening the PR (block 5 gated on env var).

---

## Notes for coding agent

- Per `docs/ux-spec.md` § "Dashboard 2 — Verdict Inspector", the 4 required sections are: filter bar, verdict table, slide-in detail panel, related events. No deviations.
- Per `../../../context/05-splunk-core/07-dashboard-studio-v2.md`, Dashboard Studio v2 supports cross-panel tokens via the `tokens` field on drilldown actions. The verdict_table drilldown sets `row_trace_id` from the clicked row; detail_panel and related_events_panel are gated on `row_trace_id` being non-empty via `visibility` rules.
- The detail panel's slide-in behavior in Dashboard Studio v2 is handled by `visibility: { conditions: [{ value: "$row_trace_id$", isNot: "" }] }` — the panel only renders when a row is clicked. No custom CSS animation needed; Splunk's default panel-appear transition handles the slide effect.
- The verdict_table columns must match the ux-spec order: timestamp, agent_id, surface, verdict_label, severity, rules (comma-joined), explanation (truncated to 80 chars via `eval explanation_truncated = substr(explanation, 1, 80)."..."`), latency_ms, trace_id.
- Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, the rules array contains up to 11 named Cisco rule classifications (Prompt Injection, PII, etc.). Use `mvjoin(rule, ", ")` to flatten for table display; keep the underlying multi-value field intact for drill-down filtering by individual rule.
- Per `docs/architecture.md` § "API schemas > Verdict", the detail panel should show: trace_id, timestamp, verdict, severity, rules (with confidence per rule), explanation (full, not truncated), classifications, modifications, surface, latency_ms. Use a key/value markdown viz or a single-event detail viz.
- The "Open in Splunk ES" button URL pattern is documented in `../../../context/05-splunk-core/01-enterprise-security-architecture.md`: `/app/SplunkEnterpriseSecuritySuite/investigation_workbench?form.search=trace_id%3D<value>`. Verify the URL pattern works against Abu's Splunk Cloud instance with ES installed before finalizing.
- Related-events query: `` `aegis_data` trace_id="$row_trace_id$" | sort _time | table _time, surface, verdict_label, severity, rules ``. This shows the agent's session timeline across all four surfaces — middleware, MCP, DefenseClaw — that share the same trace_id (via OTel trace propagation per story-core-03).
- Filter inputs bind to the verdict_table query via tokens: `` `aegis_data` $input_severity$ $input_verdict_label$ $input_agent_id$ $input_rule$ ``. Each input emits a fragment (e.g., `input_severity` emits `severity=HIGH` or `` (empty) ``); the table query interpolates them. Dashboard Studio v2 supports this via the `defaults` block and per-input `prefix`/`suffix` formatting.
- URL deep-link binding: Splunk Dashboard Studio v2 reads `?form.<input_name>=<value>` from URL automatically when input names match. So `?form.input_time.earliest=-1h&form.input_rule=PII` (from Dashboard 1 drill-down in story app-05) pre-populates the filter bar. Note: the drill-down URL in story app-05 must use the input name (`input_rule`), not the shorter `rule` form — fix story-app-05 in this story's PR if the names disagree.
- Do NOT use Classic Simple XML `<form>` syntax — this dashboard is fully Dashboard Studio v2. Mixing the two breaks the JSON parser.
- Per `docs/ux-spec.md` § "Banned patterns", do NOT add custom CSS for "slide-in animation polish" — Splunk's default transition is good enough and custom CSS triggers the AppInspect "design-system fighting" flag.
- If the JSON-in-XML file approaches 400 LOC, the safest split is to move the `dataSources` block to a sibling view via `<view ref="verdict_inspector_datasources" />`. Visualizations and inputs stay in the main file because their references to dataSources are by ID, not by inline definition.
- The Playwright test in block 5 also exercises the row-click → detail-panel-appears flow; story app-10's vision review uses the resulting screenshot to score whether the detail panel reads cleanly (no overflow, no truncation issues).

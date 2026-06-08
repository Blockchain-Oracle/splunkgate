# Story — Dashboard 3: Regulator Evidence Pack (Dashboard Studio v2)

**ID:** story-app-07-dashboard-regulator-evidence-pack
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-03-savedsearches-and-mltk-macros, story-app-04-collections-conf-kvstore-verdict-history
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** compliance officer about to screen-share an examiner walkthrough with the OCC, FFIEC, or EU AI Act DPA
**I want to** open the "Regulator Evidence Pack" dashboard, see the NIST AI RMF function table (GOVERN/MAP/MEASURE/MANAGE) populated with concrete evidence artifact counts, an SR 26-2 footnote 3 quote panel framing scope, an EU AI Act Article 6 mapping table, profile-gated HIPAA Safe Harbor 18 / PCI DSS 11.x detection panels, and a one-click "Export PDF" button
**So that** I walk into the examination with a single artifact that proves SplunkGate decisions are GOVERN/MAP/MEASURE/MANAGE-mapped, retained per jurisdictional policy, and exportable as PDF for the examiner's record — turning "we use AI safety tools" into "here are the receipts"

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml` — NEW — Dashboard Studio v2 dashboard. Wrapper: `<dashboard version="2" theme="dark" hideEdit="true"><label>SplunkGate — Regulator Evidence Pack</label><description>Examiner-grade audit artifact: NIST AI RMF function mapping, SR 26-2 scope quote, EU AI Act Article 6 mapping, HIPAA / PCI profile-gated panels, PDF export.</description><definition><![CDATA[ {JSON} ]]></definition></dashboard>`. JSON declares: 2 inputs (`input_time` defaulting to last 30 days, `input_jurisdictional_tag` dropdown — FSI/HIPAA/PUBSEC/PCI/ALL, populated from `splunkgate_profile_index_lookup`). 8 visualizations: `header_kpis` (3 single-value tiles in one panel — Coverage period, Total agent decisions logged, Decisions with examiner-grade attestation), `nist_rmf_function_table` (4 rows: GOVERN/MAP/MEASURE/MANAGE — names quoted verbatim from `../../../context/03-regulatory/01-nist-ai-rmf.md`, columns: Function / SplunkGate components contributing / Evidence artifact count), `sr_26_2_quote_panel` (markdown viz with the verbatim footnote 3 quote from SR 26-2 per `../../../context/03-regulatory/03-ffiec-occ-fed-banking.md`), `eu_ai_act_article_6_mapping` (table mapping high-risk requirements to SplunkGate surfaces with saved-search cross-references), `hipaa_safe_harbor_18_panel` (HIPAA-profile-gated via `visibility` condition on `input_jurisdictional_tag`; counts PHI detection events by Safe Harbor identifier type — 18 rows, identifier names from `../../../context/03-regulatory/05-hipaa-healthcare-ai.md`), `pci_dss_11x_panel` (PCI-profile-gated; rolling count of PCI-classified verdicts grouped by 11.x sub-requirement, per `../../../context/03-regulatory/06-pci-dss-4-0-and-ai.md`), `export_pdf_action` (markdown viz with a Splunk-native "Export PDF" link using Splunk's `/services/pdfgen/render` endpoint), `coverage_footer` (markdown showing "SplunkGate v1.0.0 generated YYYY-MM-DD by <user>"). 6 dataSources (the markdown/static panels need no datasource). Layout: header KPIs at top (12-wide), NIST table + SR quote side-by-side (6+6), EU mapping (12-wide), HIPAA + PCI conditional panels (12-wide stacked, hidden unless profile matches), export_pdf + footer at bottom. File total: target ≤ 380 LOC; if approaching 400, split markdown content blocks into a sibling include.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml exists
When  python -c "import xml.etree.ElementTree as ET; ET.parse(...)" runs
Then  exit code is 0 (well-formed XML)

Given the XML file is parsed
When  grep -E '^<dashboard version="2"' runs
Then  exactly one match

Given the XML file is parsed
When  grep 'theme="dark"' runs
Then  exactly one match

Given the CDATA JSON is extracted and parsed
When  python -c "j = json.loads(...); print(set(j['visualizations'].keys()))" runs
Then  the set is exactly {"header_kpis","nist_rmf_function_table","sr_26_2_quote_panel","eu_ai_act_article_6_mapping","hipaa_safe_harbor_18_panel","pci_dss_11x_panel","export_pdf_action","coverage_footer"}

Given the NIST RMF function table data source
When  the static rows are inspected
Then  exactly 4 rows present with first-column values "GOVERN", "MAP", "MEASURE", "MANAGE" in that order (verbatim names from NIST AI RMF 1.0 per ../../../context/03-regulatory/01-nist-ai-rmf.md)

Given the sr_26_2_quote_panel markdown content
When  grep "out of named MRM scope\|risk management practices" against it runs
Then  at least one phrase from SR 26-2 footnote 3 quoted verbatim per ../../../context/03-regulatory/03-ffiec-occ-fed-banking.md

Given the sr_26_2_quote_panel markdown
When  grep "SR 26-2\|footnote 3\|April 2026" runs
Then  attribution to the regulation present

Given the hipaa_safe_harbor_18_panel visualization config
When  the visibility condition is inspected
Then  it includes a rule gating on input_jurisdictional_tag == "HIPAA" or "ALL"

Given the pci_dss_11x_panel visualization config
When  the visibility condition is inspected
Then  it includes a rule gating on input_jurisdictional_tag == "PCI" or "ALL"

Given the eu_ai_act_article_6_mapping data source
When  the rows are inspected
Then  the table references "Article 6" and shows mapping rows with at least 4 high-risk requirements

Given the export_pdf_action markdown
When  grep "/services/pdfgen/render\|Export PDF" runs
Then  the Splunk PDF endpoint is wired

Given the XML file
When  wc -l runs
Then  output <= 400

Given a Splunk Cloud instance with the app installed
When  the dashboard loads via Playwright at /en-US/app/splunkgate_app/regulator_evidence_pack
Then  the NIST table renders with 4 rows within 5s
And   the SR 26-2 quote panel renders the verbatim text within 3s
And   profile-gated panels are hidden when input_jurisdictional_tag != HIPAA/PCI
And   browser console errors == 0

Given splunk-appinspect runs against splunk_apps/splunkgate_app/
When  the output is parsed
Then  zero "error"-severity findings against tags dashboard_studio_v2_valid, simple_xml_valid_views
```

---

## Shell verification

```bash
set -euo pipefail

# 1. File exists, XML well-formed
test -f splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml
python -c "import xml.etree.ElementTree as ET; ET.parse('splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml')"

# 2. Dashboard Studio v2 + dark theme
grep -q '<dashboard version="2"' splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml
grep -q 'theme="dark"' splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml
grep -q '<label>SplunkGate — Regulator Evidence Pack</label>' splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml

# 3. JSON structural + content checks
python - <<'PY'
import xml.etree.ElementTree as ET, json, sys, re
root = ET.parse("splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml").getroot()
defn = root.find(".//definition")
j = json.loads(defn.text)
all_text = json.dumps(j)

expected_viz = {"header_kpis","nist_rmf_function_table","sr_26_2_quote_panel","eu_ai_act_article_6_mapping",
                "hipaa_safe_harbor_18_panel","pci_dss_11x_panel","export_pdf_action","coverage_footer"}
assert set(j["visualizations"].keys()) == expected_viz, f"Viz mismatch: {set(j['visualizations'].keys())}"

# NIST functions: GOVERN, MAP, MEASURE, MANAGE in order
nist_str = json.dumps(j["visualizations"]["nist_rmf_function_table"])
for fn in ["GOVERN","MAP","MEASURE","MANAGE"]:
    assert fn in nist_str, f"NIST function {fn} missing"

# SR 26-2 quote attribution + verbatim phrase
sr = json.dumps(j["visualizations"]["sr_26_2_quote_panel"])
assert "SR 26-2" in sr or "SR26-2" in sr, "SR 26-2 attribution missing"
assert "footnote 3" in sr.lower(), "SR 26-2 footnote 3 attribution missing"
# at least one of the canonical phrases
phrases = ["out of named MRM scope","risk management practices","existing risk-management","existing risk management"]
assert any(p in sr for p in phrases), f"SR 26-2 verbatim phrase missing; found: {sr[:500]}"

# Visibility gating on profile-conditional panels
hipaa = json.dumps(j["visualizations"]["hipaa_safe_harbor_18_panel"])
assert "HIPAA" in hipaa and "input_jurisdictional_tag" in hipaa, "HIPAA panel missing profile-gate"
pci = json.dumps(j["visualizations"]["pci_dss_11x_panel"])
assert "PCI" in pci and "input_jurisdictional_tag" in pci, "PCI panel missing profile-gate"

# EU AI Act Article 6
eu = json.dumps(j["visualizations"]["eu_ai_act_article_6_mapping"])
assert "Article 6" in eu or "article 6" in eu.lower(), "EU AI Act Article 6 attribution missing"

# Export PDF endpoint
export_panel = json.dumps(j["visualizations"]["export_pdf_action"])
assert "/services/pdfgen/render" in export_panel or "Export PDF" in export_panel, \
    "Export PDF action missing"
print("All structural checks passed.")
PY

# 4. LOC cap
test "$(wc -l < splunk_apps/splunkgate_app/default/data/ui/views/regulator_evidence_pack.xml)" -le 400

# 5. Playwright smoke (gated on env)
if [ -n "${SPLUNKGATE_SPLUNK_HOST:-}" ]; then
  uv run python - <<'PY'
from playwright.sync_api import sync_playwright
import os
base = f"https://{os.environ['SPLUNKGATE_SPLUNK_HOST']}:8000/en-US/app/splunkgate_app/regulator_evidence_pack"
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(ignore_https_errors=True); page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
    # Default profile = ALL -> both gated panels visible
    page.goto(f"{base}?form.input_jurisdictional_tag=ALL", wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-test="visualization"]', timeout=15000)
    page.screenshot(path="screenshots/current/regulator_evidence_pack--desktop.png", full_page=True)
    # Profile = FSI -> HIPAA + PCI panels hidden
    page.goto(f"{base}?form.input_jurisdictional_tag=FSI", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    page.screenshot(path="screenshots/current/regulator_evidence_pack--fsi.png", full_page=True)
    assert not errors, f"console errors: {errors}"
    b.close()
PY
fi

# 6. AppInspect
uv run splunk-appinspect inspect splunk_apps/splunkgate_app/ --mode test --included-tags cloud \
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

- Per `docs/ux-spec.md` § "Dashboard 3 — Regulator Evidence Pack", the 7 required sections are: Header KPIs (3 tiles), NIST AI RMF function alignment table, SR 26-2 quote panel, EU AI Act Article 6 mapping table, HIPAA Safe Harbor 18 panel (profile-gated), PCI DSS 11.x panel (profile-gated), Export PDF action. Do not add/remove sections without re-reading ux-spec.
- Per `../../../context/03-regulatory/01-nist-ai-rmf.md`, the NIST AI RMF 1.0 functions are: **GOVERN**, **MAP**, **MEASURE**, **MANAGE** — quote these names VERBATIM (all caps, English) in the table's first column. Each row's "SplunkGate components contributing" column maps to specific surfaces: GOVERN → profiles.py + risk_factors.conf; MAP → Verdict type + OTel emission; MEASURE → saved searches + MLTK macros; MANAGE → ES RBA integration + Regulator Evidence Pack itself. The "evidence artifact count" column comes from SPL: `| stats count by component_type` against the audit-trail KV-store + savedsearches metadata.
- Per `../../../context/03-regulatory/03-ffiec-occ-fed-banking.md`, SR 26-2 (April 2026) footnote 3 reads (verbatim): "**Generative artificial intelligence (genAI), including agentic AI, is not within the named scope of [the SR 11-7 MRM framework]. Banking organizations should nevertheless apply existing risk-management practices that are commensurate with the risks posed by these technologies.**" Quote this verbatim in the `sr_26_2_quote_panel` markdown — italic blockquote formatting, with citation "SR 26-2, April 2026, footnote 3" beneath. Verify the exact phrasing in the saved context file before pasting — if the file has different exact words, use those instead.
- Per `../../../context/03-regulatory/02-eu-ai-act.md` + `../../../context/sources/docs-saved/ai-act-article-6.txt`, EU AI Act Article 6 defines high-risk AI system classification. The mapping table rows are: "Risk management system (Art. 9)" → "SplunkGate surface 1+2 middleware + MCP server"; "Data and data governance (Art. 10)" → "KV-store retention + jurisdictional_tag"; "Technical documentation (Art. 11)" → "docs/architecture.md + per-verdict explanation"; "Record-keeping (Art. 12)" → "splunkgate_verdict_history KV-store, 7-year retention"; "Transparency (Art. 13)" → "OTel trace + Verdict.explanation field"; "Human oversight (Art. 15)" → "Verdict Inspector dashboard + REVIEW label". Minimum 4 mapping rows required; including all 6 is the gold standard.
- Per `../../../context/03-regulatory/05-hipaa-healthcare-ai.md`, HIPAA Safe Harbor identifiers (18 enumerated types) are: Names, Geographic subdivisions, Dates (except year), Telephone numbers, Fax numbers, Email addresses, SSN, MRN, Health plan beneficiary numbers, Account numbers, Certificate/license numbers, Vehicle identifiers, Device identifiers, URLs, IP addresses, Biometric identifiers, Photographs, Any other unique identifying number/characteristic/code. The HIPAA panel SPL: `` `splunkgate_data` jurisdictional_tag=HIPAA earliest=$input_time.earliest$ | mvexpand classifications | stats count by classifications | search classifications IN("Names","SSN","MRN", ...) ``. Use a 1-row-per-identifier table with all 18 identifier names hardcoded as the row scaffold.
- Per `../../../context/03-regulatory/06-pci-dss-4-0-and-ai.md`, PCI DSS Requirement 11 covers "Test security of systems and networks regularly" with sub-requirements 11.1 through 11.6. The PCI panel SPL: `` `splunkgate_data` jurisdictional_tag=PCI earliest=$input_time.earliest$ | rex field=classifications "PCI[-_]11\.(?<sub>\d+)" | stats count by sub ``.
- The profile-gating mechanism uses Dashboard Studio v2's `visibility` block: `{ "conditions": [ { "type": "value", "value": "$input_jurisdictional_tag$", "isIn": ["HIPAA","ALL"] } ] }`. When the input is set to FSI or PCI, the HIPAA panel collapses to zero height; vice versa.
- The Export PDF action uses Splunk's built-in PDF generator: `/services/pdfgen/render?input-dashboard=regulator_evidence_pack&form.input_time.earliest=$input_time.earliest$`. Render as a markdown link with a button-style class. Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, Splunk Cloud's PDF service is on by default for paid tiers; document this in the dashboard description.
- The `coverage_footer` should compute its content via SPL: `| eval txt = "SplunkGate v1.0.0 generated " . strftime(now(), "%Y-%m-%d") . " by " . $env:user$ | table txt` — so the footer always reflects the current viewer + date for examiner provenance.
- The `hideEdit="true"` attribute on the `<dashboard>` element disables the "Edit" button in the toolbar — examiners shouldn't see the edit affordance during a screen-share. Splunk Dashboard Studio v2 supports this.
- Per `docs/ux-spec.md` § "Banned patterns", do NOT add custom CSS for "examiner aesthetic" — Splunk's dark theme already reads as serious enough. The PDF export uses Splunk's default render template; customizing it requires `pdfgen.conf` which is out of scope for v1.
- The two profile-gated panels MUST be hidden by default if `input_jurisdictional_tag` is unset, then become visible when matched. Splunk Dashboard Studio v2 visibility conditions support multiple `isIn` values — `["HIPAA","ALL"]` shows the HIPAA panel for either selection.
- If the file approaches 400 LOC due to the verbose HIPAA 18-identifier scaffold, split the HIPAA panel viz into a sibling view include via `<view ref="regulator_evidence_pack_hipaa">` per the same split pattern as story-app-05/06.
- The Playwright test in block 5 generates TWO screenshots — default profile (ALL) and FSI profile — so story app-10's vision review can verify the profile-gating actually hides panels visually.

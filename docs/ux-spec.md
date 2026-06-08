# UX Spec — SplunkGate (Splunk Dashboard Studio v2)

**Status:** DRAFT
**Last updated:** 2026-06-02
**Anchors EPIC-09 (Surface 4).** SplunkGate has no external web UI in v1 — Dashboard Studio v2 inside Splunk IS the UI. Three dashboards land here. Anchor source: DNS Guard AI 2025 1st-place winner (`context/11-prior-art/01-build-a-thon-2025-deep-read.md`).

---

## Anchor product (visual reference)

**Product:** Splunk DNS Guard AI (Splunkbase app 7922), 1st-place AI/ML track at Splunk Build-a-thon 2025
**Why chosen:** This is the proven winning pattern with THE judge pool. DNS Guard shipped ZERO Python, ZERO `bin/`, ZERO LLM in the Splunk app dir — pure SPL + MLTK + Dashboard Studio v2 (JSON-in-XML). Judges rewarded it. SplunkGate mirrors the visual + architectural pattern explicitly: three Dashboard Studio v2 dashboards, 8 SPL macros using `fit DensityFunction` + `fit KMeans k=2` + `anomalydetection` for ML, dark-mode-friendly Splunk-native styling.

**Cloned for reference at:** `../inspiration/Splunk-DNS-Guard-AI/`

**Files to study (all in cloned repo):**
- `Splunk-DNS-Guard-AI/default/data/ui/views/*.xml` — verbatim Dashboard Studio v2 patterns
- `Splunk-DNS-Guard-AI/default/savedsearches.conf` — search structure
- `Splunk-DNS-Guard-AI/default/macros.conf` — MLTK macro patterns

**Screenshots (immutable references — coding agent NEVER overwrites these):**
- `screenshots/anchor/dns_guard_overview.png` — captured from Build-a-thon submission
- `screenshots/anchor/dns_guard_drilldown.png`
- `screenshots/anchor/dns_guard_query_anomalies.png`

The coding agent for EPIC-09 stories `story-app-04` through `story-app-08` references these screenshots as the visual quality bar. PR diffs that deviate visually must justify the deviation.

---

## Design tokens

Splunk Dashboard Studio v2 uses Splunk's design system tokens by default. We use them as-is — overriding kills the "Splunk-native" win that DNS Guard had with the judges.

| Token | Value | Notes |
|---|---|---|
| Primary action color | `#1A8FFF` (Splunk blue) | from Splunk design system |
| Severity NONE | `#5CB85C` (green) | matches Splunk ES severity color scale |
| Severity LOW | `#F0AD4E` (amber) | |
| Severity MEDIUM | `#FF9900` (orange) | |
| Severity HIGH | `#D9534F` (red) | matches Splunk ES "critical" color |
| Background (light) | `#FFFFFF` | Splunk default |
| Background (dark) | `#1A1C20` | Splunk dark theme |
| Surface (light) | `#F8F9FA` | Card / panel background |
| Surface (dark) | `#26282C` | Card / panel background |
| Text primary | system default (Splunk-managed) | do not override |
| Font | Splunk Sans (Splunk-managed) | do not import a custom font; defeats Splunk-native goal |
| Spacing | 8/12/16/24/32 — Dashboard Studio default grid | |
| Border radius | 4px (Splunk default) — **NO `rounded-xl` or `rounded-full` panels** | |

**Banned:** any styling that screams "this isn't a Splunk app." If a coding agent is tempted to add custom CSS for "polish," they should re-read DNS Guard's source. DNS Guard wins ON Splunk-native styling, not despite it.

---

## Three dashboards

All three live at `splunk_apps/splunkgate_app/default/data/ui/views/`.

### Dashboard 1 — Agent Risk Overview (`agent_risk_overview.xml`)

**Audience:** CISO. Glance to see "are my agents safe today?"

**Sections (top to bottom on a single scrollable page):**

1. **Top KPI strip (4 single-value tiles):**
   - Total verdicts (24h)
   - BLOCK verdicts (24h) — colored by trend direction (red if up, green if down vs prior 24h)
   - HIGH-severity verdicts (24h)
   - Distinct agents observed (24h)

2. **Time-series chart:** Verdict count over 24h, stacked by `verdict.label` (ALLOW / BLOCK / MODIFY / REVIEW). Splunk Dashboard Studio v2 `line` chart with `stackMode: stacked`. Drill-down to Verdict Inspector with that time bucket filter pre-applied.

3. **Heatmap:** Rules-triggered by hour. X = hour, Y = rule name (Prompt Injection, PII, PHI, PCI, Code Detection, etc. — the 11 AI Defense rule names verbatim from `context/07-cisco-stack/01-ai-defense-deep.md`). Cell color = severity-weighted count. Drill-down to Verdict Inspector filtered to that rule + hour.

4. **Top agents by verdict count table:** agent ID, total verdicts, BLOCK count, max severity, link to agent's recent activity. Sorted by BLOCK count desc.

5. **MSJ scaling indicator** (small chart, lower-right): detection rate vs in-context message count. Cites the Anthropic Many-Shot Jailbreaking finding directly in the panel description — keeps the dashboard honest about the probabilistic ceiling per `context/01-threat-landscape/02-jailbreak-techniques.md`.

**Splunk Dashboard Studio v2 wireframe (JSON-in-XML skeleton):**

```xml
<dashboard version="2.0" theme="dark">
  <label>SplunkGate — Agent Risk Overview</label>
  <description>Real-time CISO view of AI agent safety verdicts. SplunkGate events land in the same cisco_ai_defense:* sourcetype family as the Cisco Security Cloud add-on (Splunkbase 7404).</description>
  <definition><![CDATA[
{
  "title": "SplunkGate — Agent Risk Overview",
  "visualizations": {
    "kpi_total_verdicts": { ... },
    "kpi_block_verdicts": { ... },
    "kpi_high_severity": { ... },
    "kpi_distinct_agents": { ... },
    "ts_verdicts_24h": { ... },
    "heatmap_rules_by_hour": { ... },
    "table_top_agents": { ... },
    "msj_scaling_chart": { ... }
  },
  "dataSources": {
    "ds_verdicts_24h": {
      "type": "ds.search",
      "options": {
        "query": "search index=main sourcetype=cisco_ai_defense:splunkgate_verdict earliest=-24h | timechart span=1h count by verdict_label"
      }
    },
    ...
  },
  "inputs": { "input_time": { "type": "input.timerange" } },
  "layout": { ... }
}
  ]]></definition>
</dashboard>
```

The full JSON content gets fleshed out by `story-app-05`. The story file contains the verbatim 200-line skeleton.

### Dashboard 2 — Verdict Inspector (`verdict_inspector.xml`)

**Audience:** SOC analyst + AI platform engineer. Drill-down view to investigate a specific verdict.

**Sections:**

1. **Filter bar:** time range, agent ID, rule, severity, verdict label. All driven by URL parameters so deep-links from Dashboard 1 work.

2. **Verdict table:** one row per verdict. Columns: timestamp, agent_id, surface (mw_model / mcp_judge_tool / etc.), verdict_label, severity, rules (comma-separated), explanation (truncated at 80 chars with full-text on hover), latency_ms, trace_id.

3. **Detail panel** (slides in on row click): full Verdict object pretty-printed:
   - Full input text
   - Full agent context (model name, system prompt summary, tool list at time of call)
   - Full evaluator chain (which classifiers ran, in what order, each one's response)
   - Verdict
   - Severity
   - Rules with confidence scores
   - Foundation-Sec explanation (full)
   - OTel trace ID with link to Splunk APM (if instrumented)
   - "Open in Splunk ES" button — pre-fills an ES investigation with the trace_id

4. **Related events** (lower panel): events from the same trace_id across all surfaces — shows the agent's full session leading up to and following the verdict.

### Dashboard 3 — Regulator Evidence Pack (`regulator_evidence_pack.xml`)

**Audience:** Compliance officer + external examiner (OCC, FFIEC, EU AI Act DPA). The dashboard a CISO would screen-share during an examination.

**Sections:**

1. **Header KPIs (3 tiles):**
   - "Coverage period" (configurable date range, defaults to last 30 days)
   - "Total agent decisions logged" (the audit-trail volume claim)
   - "Decisions with examiner-grade attestation" (= total — explicit subset is misleading; this confirms 100% have full provenance)

2. **NIST AI RMF function alignment table:** 4 rows (GOVERN / MAP / MEASURE / MANAGE — verbatim function names per `context/03-regulatory/01-nist-ai-rmf.md`). Each row shows which SplunkGate components contribute to that function + a count of evidence artifacts (saved searches, KV-store entries, OTel events).

3. **SR 26-2 quote panel** (text only): displays the verbatim footnote 3 from SR 26-2 (`context/03-regulatory/03-ffiec-occ-fed-banking.md`) that excludes GenAI/agentic AI from named scope but says banks should apply existing risk-management practices. SplunkGate positions itself within that frame.

4. **EU AI Act Article 6 mapping** (table): high-risk AI system requirements + which SplunkGate surface satisfies each (with cross-references to specific saved searches).

5. **HIPAA Safe Harbor 18-identifier dashboard** (only visible if `risk_profile=HIPAA` lookup loaded): count of PHI detection events by identifier type (1 row per identifier) over coverage period.

6. **PCI DSS sub-requirement 11.x detection event count** (only visible if `risk_profile=PCI`): rolling count of PCI-classified verdicts.

7. **"Export PDF" action:** Splunk's built-in dashboard PDF export, with a custom CSS that styles the PDF for examiner presentation — header with CISO contact, footer with "SplunkGate vX.Y.Z generated YYYY-MM-DD," embedded NIST/SR/EU citations.

---

## Demo shape rule

For the 90-second demo:

1. Start on **Dashboard 1 — Agent Risk Overview**. Counters live. Heatmap shows recent activity.
2. Run the malicious-prompt demo script in a sidecar terminal (visible in screen-share).
3. Counter ticks up; heatmap cell darkens.
4. Click into the heatmap cell → land on **Dashboard 2 — Verdict Inspector** filtered to that hour + rule.
5. Click the new row → detail panel slides in. Show the full verdict + explanation.
6. Click "Open Regulator Evidence Pack" link → land on **Dashboard 3**. Click "Export PDF for OCC examiner." PDF generates. Open PDF. Done.

That's the full demo flow. Coding agent for `story-demo-01-script` writes this verbatim.

---

## Required structural elements (per Splunk Dashboard Studio v2 conventions)

**Every dashboard:**
- `<label>` set to "SplunkGate — <name>"
- `<description>` set with a one-liner pointing back to the data source sourcetype
- `theme="dark"` set on `<dashboard>` (matches DNS Guard winner)
- `version="2.0"` (Dashboard Studio v2)
- Time-range input at the top
- "Last updated" stamp using `now()` in a markdown panel

**No external CSS/JS injected.** Splunk's design system handles styling. Coding agents adding `<style>` blocks need to justify in the PR.

---

## Banned patterns

- Custom fonts imported via `@font-face` — Splunk Sans only
- Light-mode-only color choices that don't degrade to dark — Splunk's dark mode is the default we ship
- `rounded-full` or `rounded-2xl`-shaped panels — Splunk uses `4px` border radius across the board
- Loading screens longer than 500 ms — split the query; use `tstats` where possible
- More than 3 nested drill-downs — judges and CISOs lose track
- Dashboard panels with > 20 inline color overrides — strong signal of design-system fighting

---

## Visual loop validation

After any `*.xml` (Dashboard Studio JSON-in-XML) edit, the PostToolUse hook (drops via `sahil-visual-loop`):

1. Spins up a Splunk Docker locally (or hits a CI-managed instance) loaded with synthetic SplunkGate verdict events
2. Playwright loads each dashboard
3. Captures screenshot at `screenshots/current/<dashboard>--desktop.png`
4. `odiff` compares vs `screenshots/anchor/<dashboard>--desktop.png`
5. Sends both to Opus 4.7 vision-review (story `story-app-09`)
6. Verdict JSON lands at `.claude/last-review.json`
7. If `verdict !== "ok"`: fix before commit

**Passing threshold:** `slop_score ≤ 2 AND blocking_count = 0`.

---

## Accessibility (light touch — Splunk handles most)

- All panels have `<description>` text (Splunk reads to screen readers)
- All color encoding is paired with text labels (a red KPI also says "BLOCK")
- Heatmap has alt-text drill-down to a table view

Coding agent for `story-app-10` runs `pa11y` against each dashboard URL once Splunk Cloud demo is live.

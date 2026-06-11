# Splunk-App Redesign — Designer Brief

**For:** the designer who delivered `~/Downloads/ageis(1)/` (landing + docs)
**About:** the SplunkGate Splunk app (`splunk_apps/splunkgate_app/`)
**Owner:** Abu
**Date:** 2026-06-11
**Deadline pressure:** Devpost submission 2026-06-15 09:00 PDT

---

## TL;DR

The Splunk app dashboards today are **Dashboard Studio v2** JSON wrapped in
an XML envelope, rendered in Splunk's native navy palette. Per
`grounding.md` line 88 + Brand Kit line 231, the design intent was
"Splunk-native navy by design — only the marketing surfaces use the warm
palette." The dashboards work (FIELDALIAS bug fixed Jun 9, see
`docs/audits/2026-06-11-docs-and-submission-audit.md`) but they look
generic-Splunk, not on-brand with the landing page.

This brief lays out **three real options** with effort estimates and
risk profile. Abu picks; the designer renders.

---

## What we have today

```
splunk_apps/splunkgate_app/
├── default/data/ui/views/
│   ├── agent_risk_overview.xml      ← Dashboard Studio v2, navy
│   ├── verdict_inspector.xml         ← Dashboard Studio v2, navy
│   ├── regulator_evidence_pack.xml   ← Dashboard Studio v2, navy
│   └── splunkgate_setup.xml          ← Simple XML form (post-MLTK setup)
├── default/data/ui/nav/default.xml   ← Nav bar
├── default/app.conf
├── META-INF/manifest.json            ← Splunk Cloud platformRequirements 10.4+
├── static/                           ← appIcon{,_2x,Alt,Alt_2x}.png
└── LICENSE / README
```

Three operational dashboards + a setup form. The shipped tarball is
`dist/splunkgate_app-1.0.0.tgz` — byte-deterministic, AppInspect-clean.

Visual sample to compare against: `screenshots/docs-splunk.png` and the
designer's own Brand Kit `id="art-shot"` section (the "authentic Splunk-
native navy" reference panel).

---

## The technical landscape (research, 2026-06-11)

Splunk app developers have **three** rendering surfaces, in increasing
order of customisation:

### Surface 1 — Simple XML
- Legacy `<dashboard><row><panel>` markup. Deprecated for new apps.
- Out of scope; do not consider.

### Surface 2 — Dashboard Studio v2 (our current approach)
- JSON-in-XML wrapper, theme={light|dark}, absolute or grid layout.
- Customisable per-chart palette (`seriesColors`, `fieldColors`), per-
  panel background, fonts.
- Dashboard-level `defaults` block can theme all charts at once.
- **Constraints (Splunk Cloud Platform 10.4+):**
  - Background colour is hex; arbitrary CSS not allowed.
  - Fonts are pinned to Splunk Platform Sans; we cannot ship our own.
  - Branding hex tokens (the warm `--paper #F1ECE1`, the `--accent
    #BC3A26`) work as `seriesColors` and `backgroundColor` overrides.
  - AppInspect blocks arbitrary `web.conf` — no custom `[settings]`.
- Sources: [Dashboard Studio overview][1], [Background customisation][2],
  [Color palette customisation][3].

### Surface 3 — Splunk UI Toolkit (SUIT) — custom React inside the app
- **The official modern alternative.** SUIT is the React framework
  Splunk built and uses across its own product surface — Dashboard
  Studio is itself built on SUIT's Dashboard Framework.
- Three packages:
  - `@splunk/create` — scaffolder for a new app
  - `@splunk/react-ui` — React component library (button, card, table,
    modal, etc.)
  - `@splunk/dashboard-framework` — the rendering engine; accepts the
    same JSON Dashboard Studio uses
- Lets you build a **custom React page** as a Splunk view — full HTML,
  full CSS, full fonts, full palette. Bundled into `static/` and loaded
  via `default/data/ui/views/your_view.xml` with a `<view>` element.
- **Constraints (Splunk Cloud Platform 10.4+):**
  - **AppInspect rejects static dependencies** — the bundle must be
    self-contained (no `<script src="https://cdn…">`).
  - **`web.conf` restricted** — only `[endpoint:*]` and `[expose:*]`
    stanzas; no custom routing.
  - Bundle size matters for Splunk Cloud upload (no hard cap, but
    review time scales with size).
  - Requires Node toolchain in dev + a build step in CI to produce
    minified, source-mapped bundles before tarball.
- Boilerplate reference: [`robertsobolczyk/splunk-react-app`][4]
- Sources: [Splunk UI Toolkit / Build apps][5], [Splunk views][6],
  [Building customised dashboards with SUIT][7], [Lantern SUIT
  guide][8], [A new way to look like Splunk][9].

[1]: https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/dashboard-studio/10.4/introduction-to-splunk-dashboard-studio/what-is-splunk-dashboard-studio
[2]: https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/dashboard-studio/10.2/create-a-dashboard-in-dashboard-studio/create-a-dashboard-in-dashboard-studio/modify-the-background
[3]: https://www.splunk.com/en_us/blog/platform/dashboard-studio-dashboard-customization-made-easy.html
[4]: https://github.com/robertsobolczyk/splunk-react-app
[5]: https://dev.splunk.com/enterprise/docs/developapps/createapps/buildapps/
[6]: https://dev.splunk.com/view/SP-CAAAEM7
[7]: https://lantern.splunk.com/Platform_Data_Management/Transform_Data/Building_customized_dashboards_with_the_Splunk_UI_Toolkit
[8]: https://lantern.splunk.com/Splunk_Platform/Product_Tips/Enterprise/Creating_better_custom_applications_with_the_Splunk_UI_Toolkit
[9]: https://www.splunk.com/en_us/blog/platform/a-new-way-to-look-like-splunk.html

---

## The three real options

### Option A — Theme the existing Dashboard Studio JSON (LOW effort)

**What:** keep all three dashboards in Dashboard Studio v2 / navy chrome,
but customise the per-chart palette and panel backgrounds to lean toward
our `--paper #F1ECE1` / `--accent #BC3A26` accent family. Splunk's chrome
(top bar, side rails, breadcrumbs) stays navy — that's a platform constant.

**What the designer ships:**
- A revised JSON `defaults` block per dashboard (3 dashboards × 1 block)
  pinning: dashboard `backgroundColor`, `seriesColors`, KPI tile
  `valueColor`, table header colour
- A swatch list of hex tokens the engineer (us) drops in
- Two annotated screenshots showing "before navy" vs "after themed"

**Effort:** ~half a day designer time + ~half a day engineering wire-in
**Risk:** zero — Splunk Cloud accepts JSON customisations natively;
AppInspect doesn't flag colour overrides
**Result:** the dashboards still LOOK Splunk-native (judges/SOC analysts
expect that), but the accent reads consistent with the landing
**Tradeoff:** can't get the warm `--paper` background through; Splunk's
chrome will always frame the page in navy. The accent + KPI colours
match. The shell doesn't.

### Option B — Build a custom SUIT React view (HIGH effort, HIGH risk)

**What:** replace the three Dashboard Studio dashboards with a single
custom React Splunk view (or a small set of them). Full `--paper`
background, full Newsreader + Hanken Grotesk fonts (bundled via `static/`),
full `--accent` accent — pixel-equivalent to the landing page.

**What the designer ships:**
- HTML/CSS/JSX prototype matching the existing landing-page Brand Kit
  but with Splunk-native data shapes (charts, KPIs, tables, drill-down)
- Component-level annotations: Splunk Search SDK call shape per
  component (engineer wires the data)

**What engineering does:**
- `@splunk/create` scaffold inside `splunk_apps/splunkgate_app/src/` (new)
- Port the Brand Kit's CSS variables into the SUIT app
- Replace the 3 dashboards' XML stubs with `<view>` references to the
  built React bundle
- Add a Node build step to `scripts/build_splunk_app_tgz.sh` that emits
  the bundle into `static/` before tarball assembly
- Re-validate AppInspect — verify no static dependencies, web.conf
  stays clean, bundle is self-contained
- Re-test in `splunkgate-local` container against synthetic events

**Effort:** ~3-5 days designer + ~3-5 days engineering, in parallel
**Risk:** **HIGH for the 4-day deadline.** AppInspect failures here are
not always obvious — a stray `<script>` reference, an inline
`fetch('https://…')`, a missing `META-INF/manifest.json` field can all
fail the gate. Re-build cycle is slow because each tarball must be
rebuilt + re-inspected. Bundle size could push us into a "long review"
queue.
**Result:** the Splunk app looks like the landing page. The "4 surfaces,
one verdict, one design language" pitch lands hard.
**Tradeoff:** if it breaks Jun 14 with a Devpost-blocking AppInspect
failure, we have no fallback unless we keep the Dashboard Studio version
as a parallel branch.

### Option C — Hybrid (MEDIUM effort, MEDIUM risk) — RECOMMENDED

**What:** keep the **operational** dashboards (Agent Risk Overview,
Verdict Inspector) in themed Dashboard Studio v2 / navy, where SOC
analysts and CISO live. They are productivity tools — the SOC expects
the Splunk chrome there. Apply Option A's palette tweaks.

Build **only the Regulator Evidence Pack** as a SUIT custom React view.
That's where the on-brand "this is OUR product, not just a Splunk app"
storytelling lives — the NIST RMF mapping, the SR 26-2 verbatim quote,
the EU AI Act framing, the "Export PDF for OCC examiner" button. The
audience is the buyer, not the operator. Different audience, different
chrome makes sense.

**What the designer ships:**
- Option A's JSON theming for the two operational dashboards
- A SUIT-targeted HTML/CSS/JSX prototype for the Regulator Evidence
  Pack, structured to bundle into `splunk_apps/splunkgate_app/static/`
- Same Brand Kit references (warm `--paper`, Newsreader serif for the
  SR 26-2 quote, etc.)

**What engineering does:**
- Wire Option A JSON for the two operational dashboards (½ day)
- Scaffold one SUIT view for the Evidence Pack only (1-2 days)
- Replace `regulator_evidence_pack.xml`'s `<dashboard>` element with a
  `<view>` element pointing at the bundled React component
- AppInspect-validate; keep the original `.xml` in a `.bak` so we can
  revert if SUIT fails

**Effort:** ~2-3 days designer + ~2 days engineering
**Risk:** medium — if the SUIT view fails AppInspect, we keep the navy
Dashboard Studio version of the Evidence Pack and only ship Option A's
theming. Either path is a viable submission.
**Result:** the dashboards SOC analysts use stay where they expect them
to be. The dashboard the **buyer** sees is on-brand with the landing.
The "4 surfaces, one verdict" story holds without forcing every surface
into a single palette.

---

## Recommendation

**Option C — Hybrid.** Reasons:

1. **Honours grounding.md** ("Splunk-native navy by design") for the
   operational surfaces while still creating a brand moment on the buyer-
   facing one.
2. **Bounded risk** — if SUIT fails AppInspect, we have a working
   Dashboard Studio Evidence Pack as fallback. Option B has no fallback.
3. **The buyer-facing dashboard IS the prize-track signal** — the
   Regulator Evidence Pack is what backs the "Security track" framing.
   The Splunk app proves "I built a real Splunk app." SOC dashboards
   prove "I respect operator workflow." Hybrid lets each surface do its
   actual job.

If we're already 24 hours behind on the demo recording (story-demo-01),
**fall back to Option A**. A polished navy palette with consistent
accent reads better than a half-finished SUIT view that doesn't
AppInspect-clean.

---

## What we are NOT asking the designer for

- Mobile responsive dashboards. Splunk Cloud doesn't render dashboards
  on mobile. Skip.
- Animation in the dashboards. Splunk renders static — no IO scrolls,
  no terminal cascades. The animations live on the marketing site only.
- Replacing Splunk chrome (top bar, side rails). Not possible inside
  Splunk Cloud Platform constraints; AppInspect rejects it.
- A custom font for Dashboard Studio dashboards. Splunk pins
  `Splunk Platform Sans`; only the SUIT view can ship its own fonts
  (Hanken Grotesk + Newsreader + JetBrains Mono).

---

## Content accuracy notes (same as the architecture-diagram-brief)

- Sourcetype is verbatim `cisco_ai_defense:splunkgate_verdict` —
  underscore, not dash.
- The three dashboards' names are **Agent Risk Overview**, **Verdict
  Inspector**, **Regulator Evidence Pack**. Don't rename.
- Foundation-Sec is EXPLAINER only (ADR-003) — never shown as a
  classifier or a judge.
- Cisco AI Defense rules are 11 named rules — list available on request.
- MITRE ATLAS technique for Prompt Injection: `AML.T0051`.
- SR 26-2 footnote 3: verbatim quote required; live in the Verbatim
  callout style from the landing page Brand Kit.

---

## Open decisions Abu needs to make

1. **Pick A / B / C.** Default if no answer by EOD: A (lowest risk,
   smallest delta to ship).
2. **If C: does the Evidence Pack PDF export need to live in the SUIT
   view, or does the existing "Export PDF (browser print)" pattern
   still ship?** (the print path is zero-effort and works today.)
3. **Are we OK shipping the navy chrome around the warm SUIT view?**
   Splunk Cloud won't let us replace the page header — the React view
   sits inside the navy Splunk shell. Acceptable visual? (Most apps
   that ship a SUIT view live with this.)

---

## What this brief is NOT

This is not a do-it-or-die ask. The dashboards we have today
**function** and they're AppInspect-clean. They were debugged on Jun 9
(FIELDALIAS fix) and the events render against synthetic data. If
nothing in this brief gets touched, the submission still ships.

The brief exists so the designer can plan their time and so we can
make an informed choice rather than default into Option A by accident.

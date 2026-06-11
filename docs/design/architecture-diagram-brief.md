# Architecture Diagram — Designer Brief

**Output:** SVG at `docs/assets/architecture.svg` (export PNG at `docs/assets/architecture.png`)
**Canvas:** 1180 × 720 px, background `#F1ECE1` (--paper from Brand Kit)
**Title:** "How a verdict travels"
**Subtitle:** `agent → judgment → verdict → OpenTelemetry → Splunk`
**Palette / fonts:** verbatim from `Brand Kit.html` (Hanken Grotesk / Newsreader / JetBrains Mono)

The Brand Kit HTML already contains the canonical visual design at `id="art-arch"`. Use that as
the authoritative reference — the brief below documents only the content that must be accurate.

---

## Layout

Three columns, equal height, centered vertically. The center column is visually heavier (dark card).
Thin arrow indicators between columns (→) communicate left-to-right flow.
Footer line at bottom: monospaced, ink-3 color.

---

## Column 1 — "SURFACES · ANY AGENT"

Column tag (uppercase mono, ink-3): `SURFACES · ANY AGENT`

Three card boxes (card bg, rule border, 5px radius), from top to bottom:

| box | primary label | secondary label |
|-----|--------------|-----------------|
| S1  | `S1 · splunkgate-mw` | `splunklib.ai middleware` |
| S2  | `S2 · splunkgate-mcp` | `MCP server tool` |
| S3  | `S3 · DefenseClaw` | `HTTP gateway delta` |

Notes:
- S4 (`splunkgate_app`) is intentionally absent here — it appears in Column 3.
- Primary labels in JetBrains Mono 600, secondary in JetBrains Mono 400 ink-3.

---

## Column 2 — "SPLUNKGATE JUDGMENT CORE" (dark card)

Background: `#17140E` (--dk). Inner border: `rgba(240,234,222,.14)` (--dk-rule).
Column tag (mono, dk-ink2): `SPLUNKGATE JUDGMENT CORE`
Sub-tag inside dark card (mono 11px, dk-ink2): `classify → explain → decide`

Three inner rows:

| row | left accent | primary label | secondary label |
|-----|-------------|--------------|-----------------|
| Classifier | `#BC3A26` (--accent, 2px left border) | `Cisco AI Defense` | `binary classifier · 11 rules` |
| Explainer  | `#E2A53E` (amber, 2px left border)    | `Foundation-Sec`   | `explainer · WHY-string` |
| Verdict    | full `#BC3A26` fill (--accent)        | `Verdict`          | right-aligned: `BLOCK · HIGH` |

Verdict row: white text on accent red, spans full width of dark card. Monospaced.

---

## Column 3 — "LAND & CONSUME · S4"

Column tag (uppercase mono, ink-3): `LAND & CONSUME · S4`

Three card boxes, from top to bottom:

| box | primary label | secondary label |
|-----|--------------|-----------------|
| OTel | `OpenTelemetry` | `gen_ai.evaluation.result` |
| HEC  | `Splunk HEC`    | `cisco_ai_defense:splunkgate_verdict` |
| Dashboards | `3 dashboards` | `risk · inspector · evidence pack` |

The Dashboards box uses the accent style: `#BC3A26` 3px left border, `rgba(188,58,38,.09)` background,
primary label in `#93291A` (--accent-deep).

---

## Header row

Shield glyph SVG (24×28 px, path from Brand Kit): `fill:#1D1A13`
Title: "How a verdict travels" — Newsreader serif 500 30px, ink color
Subtitle: `agent → judgment → verdict → OpenTelemetry → Splunk` — JetBrains Mono 12px, ink-3

---

## Footer

Full-width, bottom of canvas, centered:
```
primary-source-grounded at every hop · trace_id chains all four surfaces
```
JetBrains Mono 11.5px, ink-3 (`#938C7B`).

---

## Content accuracy notes (repo → grounding.md wins over brief)

- Package names use `splunkgate_mw`, `splunkgate_mcp` (not `aegis_mw` / `aegis_mcp` — renamed in ADR-013).
- Sourcetype verbatim: `cisco_ai_defense:splunkgate_verdict` (one word, underscore-separated).
- The three dashboards are: Agent Risk Overview, Verdict Inspector, Regulator Evidence Pack.
- Foundation-Sec is EXPLAINER only (ADR-003) — never shown as a classifier.
- Cisco AI Defense has 11 named rules — the diagram does not need to list them.
- `gen_ai.evaluation.result` is the OTel event name (GenAI semantic conventions).

---

## What we are NOT asking for

- Dark-mode variant (not needed for README or Devpost submission; add if time permits).
- Animation.
- Splunk dashboard screenshot (that is a separate `Brand Kit.html` section: `id="art-shot"`).

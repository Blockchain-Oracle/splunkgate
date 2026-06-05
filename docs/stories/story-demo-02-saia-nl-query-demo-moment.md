# Story — SAIA-driven NL→SPL demo moment showing Splunk-native integration

**ID:** story-demo-02-saia-nl-query-demo-moment
**Epic:** EPIC-11 — Demo video assets + README + architecture diagrams
**Depends on:** story-app-05-dashboard-agent-risk-overview, story-app-13-synthetic-verdict-emitter-script, story-demo-01-screencast-and-script
**Estimate:** ~1h (mostly recording, no code)
**Status:** PENDING
**Added:** 2026-06-05 (per ADR-013 — integration adds; SAIA installed in tenant today)

---

## User story

**As a** judge watching the < 3-minute demo video
**I want to** see a SOC analyst type a natural-language question ("show me the agents Aegis blocked in the last hour") into Splunk AI Assistant (SAIA) and watch SAIA write the SPL that surfaces Aegis verdicts in the same dashboard the live demo just populated
**So that** the demo concretely proves Aegis is a *Splunk-native* integration that fits naturally into existing AI-assisted SOC workflows — not a bolted-on side project

---

## Why this matters (scoring levers)

| Criterion | How this story scores |
|---|---|
| **Design** (25%) | Customer-Success judges (Refael Botbol Weiss in particular — Tech Evangelist, optimizes for storytelling) reward demo narratives that show workflow integration. NL→SPL via SAIA is the most-current Splunk-native UX pattern. |
| **Technological Implementation** (25%, tiebreaker) | Concretely uses Splunkbase app 7245 (SAIA, installed in Abu's tenant 2026-06-05). Signal: we shipped against the latest Splunk AI surface, not the 2023 search bar. |
| **Best Use of Splunk Developer Tools bonus prize** | SAIA is a Splunk Developer Tool by reasonable definition (AI Assistant for SPL, ships from Splunk LLC). Citing it in the demo concretely supports the bonus prize claim. |

---

## File modification map

- `docs/demo/saia-demo-script.md` — NEW — ~80 lines. Frame-by-frame script for the SAIA demo scene (Scene 4 of the < 3-min video). See "Demo scene structure" below.
- `splunk_apps/aegis_app/default/data/ui/views/aegis_saia_demo_starter.xml` — NEW — Splunk Dashboard Studio v2 XML stub that is the dashboard SAIA's generated SPL populates. Minimal — just enough to show the dashboard reacts. (May be subset of `dashboard_agent_risk_overview.xml` from story-app-05.)
- `docs/stories/story-demo-01-screencast-and-script.md` — UPDATE — append a reference to this story's `saia-demo-script.md` so demo-01 (the umbrella screencast story) doesn't double-author the SAIA scene.

The recording itself is delivered as a video artifact, not a file in the repo. Per the existing demo-01 pattern, the YouTube link lands in `README.md`'s headline section.

---

## Demo scene structure (Scene 4 of the < 3-min video)

The full 3-min demo has 4 scenes per story-demo-01:
- Scene 1 (0:00–0:30): Splunk dashboard "Agent Risk Overview" showing zero blocks, support agent running normally
- Scene 2 (0:30–1:30): Malicious prompt sent → `model_middleware` fires → BLOCK verdict, console log, dashboard counter ticks
- Scene 3 (1:30–2:15): Verdict Inspector drill-down → full provenance → Regulator Evidence Pack PDF export
- **Scene 4 (2:15–2:45): THIS STORY** — SAIA NL→SPL demo
- Scene 5 (2:45–3:00): Close (Aegis logo, GitHub URL, Apache-2.0)

### Scene 4 — exact narrative

```
[Visual: split screen — left: Splunk Search UI with SAIA panel open in top-right.
         right: the Agent Risk Overview dashboard from Scene 1.]

Narrator (voiceover, ~25 words):
"Aegis is Splunk-native. Any SOC analyst can ask the AI Assistant about agent
risk in plain English — no SPL knowledge required."

[Action: analyst types in SAIA chat input:]
"Show me which agents Aegis blocked in the last hour and what rules fired."

[SAIA generates SPL, displays it in a code block. Narrator reads first line:]
"SAIA writes:    index=cisco_ai_defense sourcetype=cisco_ai_defense:aegis_verdict
                 verdict=BLOCK earliest=-1h
                 | stats count by agent_id, rule_name"

[Action: analyst clicks "Run Search" inside SAIA panel.]

[Result: the right-side Agent Risk Overview dashboard refreshes; the
 "Blocks by Rule" panel updates with the same data, illustrating that
 SAIA's NL→SPL output and our dashboard converge on the same Aegis events.]

Narrator (~15 words):
"The result lands in the same dashboard. Aegis verdicts live in the SOC
analyst's existing workflow, not in a parallel app."

[Cut to Scene 5.]
```

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given docs/demo/saia-demo-script.md exists
When  the file is parsed
Then  it contains a "Scene 4" heading AND the verbatim natural-language question "Show me which agents Aegis blocked in the last hour and what rules fired."

Given docs/demo/saia-demo-script.md
When  the file is grepped for "sourcetype=cisco_ai_defense:aegis_verdict"
Then  count ≥ 1

Given docs/demo/saia-demo-script.md
When  the file is grepped for "Splunkbase app 7245"
Then  count ≥ 1 (credits the SAIA app explicitly)

Given splunk_apps/aegis_app/default/data/ui/views/aegis_saia_demo_starter.xml exists
When  the file is parsed as XML
Then  it is well-formed AND contains a `<dashboard>` (Classic XML wrapper per ADR-008) AND inside it the JSON-in-XML body references the same panel IDs as dashboard_agent_risk_overview.xml

Given the final YouTube demo video URL (set in README.md by story-demo-01)
When  the README is grepped for that URL
Then  count ≥ 1 (the video is linked from the README headline section)

Given the script and Scene 4
When  scene timings are computed from the script
Then  total demo length is < 180 seconds (the 3-min hackathon submission limit)
```

---

## Shell verification

```bash
# Script exists and contains the required phrases
grep -q "Scene 4" docs/demo/saia-demo-script.md || exit 1
grep -q "Show me which agents Aegis blocked" docs/demo/saia-demo-script.md || exit 1
grep -q "sourcetype=cisco_ai_defense:aegis_verdict" docs/demo/saia-demo-script.md || exit 1
grep -q "Splunkbase app 7245" docs/demo/saia-demo-script.md || exit 1

# Dashboard XML is well-formed
xmllint --noout splunk_apps/aegis_app/default/data/ui/views/aegis_saia_demo_starter.xml || exit 1

echo "OK"
```

---

## Notes for coding agent

- **SAIA is installed at app id 7245 in Abu's Splunk Cloud tenant `prd-p-t9irr.splunkcloud.com`** as of 2026-06-05 (per task #77 / Playwright install log). The recording itself happens in that tenant.
- The SOC-analyst NL question must match what SAIA actually generates — if SAIA's generated SPL diverges from the verbatim line in the script, **update the script to match SAIA's output**, not vice versa. Authentic SPL > pre-scripted SPL. Judges will spot a fake.
- Per `context/06-splunk-ai-stack/02-saia-ai-assistant-for-spl.md`, SAIA has both a "write SPL" and an "explain SPL" mode. This story uses the write mode only.
- If SAIA refuses to generate the SPL (e.g., it doesn't know about `sourcetype=cisco_ai_defense:aegis_verdict` because no events have been indexed yet), **first run story-app-13-synthetic-verdict-emitter-script** so SAIA's index awareness includes the Aegis sourcetype. That story's dependency is locked here.
- Use OBS Studio or QuickTime screen recording. Compress final MP4 to < 50 MB so the YouTube upload completes quickly.
- DO NOT use copyrighted music. Per hackathon rules: "No unlicensed third-party trademarks, music, or copyrighted material." Either silent narration or free Creative Commons audio (creativecommons.org or YouTube Audio Library).
- The script lives in `docs/demo/` so future contributors can update it independently of the recording itself.

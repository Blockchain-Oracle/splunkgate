# Story — MITRE ATLAS technique-ID lookup mapping Cisco AI Defense rules

**ID:** story-app-14-mitre-atlas-technique-mapping
**Epic:** EPIC-09 — Surface 4 (Splunk app)
**Depends on:** story-app-02-props-transforms-for-aegis-verdict-sourcetype
**Estimate:** ~1h
**Status:** PENDING
**Added:** 2026-06-05 (per ADR-013 — scope pivot integration adds)

---

## User story

**As a** SOC analyst already running detection rules from the MITRE ATLAS AI Threat Detection app (Splunkbase 8527)
**I want to** see each Aegis verdict tagged with the MITRE ATLAS technique ID(s) corresponding to its Cisco AI Defense rule names
**So that** an Aegis block on a prompt-injection attempt pivots directly into my ATLAS-aligned detection workflow without re-mapping by hand

---

## Why this matters

Three judge-scoring levers in one cheap story:

1. **Quality of the Idea** — Open-standards interoperability with MITRE ATLAS is a recognizable signal. Most submissions invent their own rule taxonomies; we adopt the industry one.
2. **Technological Implementation** — Real Splunk-app integration mechanic (`lookup` + `eval`) judged favorably by Abhishek Nair (PM Enterprise Security, cares about CIM/ES alignment) and James Ronayne (Staff Security Consultant, cares about open-standards rigor).
3. **Potential Impact** — Henry Robalino (FSI judge) values verdicts that drop into existing SOC workflows; ATLAS technique IDs are how that mapping happens.

---

## File modification map

- `splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv` — NEW — CSV with columns `rule_name,atlas_technique_id,atlas_technique_name,atlas_tactic_id`. Maps each of the 11 Cisco AI Defense rule names to MITRE ATLAS technique IDs. See "Acceptance criteria" for the exact required rows.
- `splunk_apps/aegis_app/default/transforms.conf` — UPDATE — add a `[atlas_technique_mapping]` stanza pointing at the CSV.
- `splunk_apps/aegis_app/default/savedsearches.conf` — UPDATE — modify the `aegis_verdict_ingest` saved search (defined in story-app-03) to enrich verdicts with `atlas_technique_id` + `atlas_tactic_id` via `lookup atlas_technique_mapping rule_name OUTPUT atlas_technique_id, atlas_technique_name, atlas_tactic_id`.
- `docs/architecture.md` — UPDATE — add a one-line entry to ADR-005's "Aegis events emit to `cisco_ai_defense:aegis_verdict` sourcetype" noting that the sourcetype also carries ATLAS technique IDs as enriched fields.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv exists
When  `awk -F',' 'NR>1 {print $1}' splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv | sort -u | wc -l` runs
Then  the count is 11 (one row per canonical Cisco AI Defense rule name)

Given the CSV
When  the file is grepped for "Prompt Injection,AML.T0051" (the canonical ATLAS technique for LLM Prompt Injection)
Then  exactly 1 match

Given the CSV
When  the file is grepped for the rule names "PII", "PHI", "PCI" (data-disclosure rules)
Then  all three are mapped to AML.T0057 ("LLM Data Leakage") or a more specific child technique

Given the CSV
When  every row is parsed
Then  every atlas_technique_id matches the regex `^AML\.T[0-9]{4}(\.[0-9]{3})?$` (MITRE ATLAS technique ID format)

Given splunk_apps/aegis_app/default/transforms.conf
When  the file is parsed for the [atlas_technique_mapping] stanza
Then  it references `filename = atlas_technique_mapping.csv`

Given splunk_apps/aegis_app/default/savedsearches.conf
When  the `aegis_verdict_ingest` saved search definition is read
Then  it contains the literal token `lookup atlas_technique_mapping rule_name`
```

---

## Shell verification

```bash
# 11 unique rule_name entries
test "$(awk -F',' 'NR>1 {print $1}' splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv | sort -u | wc -l)" -eq 11 || exit 1

# Every ATLAS technique ID is well-formed
awk -F',' 'NR>1 {print $2}' splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv | grep -vE '^AML\.T[0-9]{4}(\.[0-9]{3})?$' && exit 1

# The 11 Cisco AI Defense rules are all present
for rule in "Code Detection" "Harassment" "Hate Speech" "PCI" "PHI" "PII" "Prompt Injection" "Profanity" "Sexual Content & Exploitation" "Social Division & Polarization" "Violence & Public Safety Threats"; do
  grep -qF "$rule," splunk_apps/aegis_app/lookups/atlas_technique_mapping.csv || { echo "Missing rule: $rule"; exit 1; }
done

echo "OK"
```

---

## Notes for coding agent

- **Canonical ATLAS technique source:** https://atlas.mitre.org/techniques — fetch the most-current technique IDs at implementation time. Do NOT invent IDs.
- **The 11 Cisco AI Defense rule names are locked verbatim** per `context/07-cisco-stack/01-ai-defense-deep.md`. Match casing exactly so the lookup join works.
- **For "Prompt Injection":** map to **AML.T0051** (LLM Prompt Injection) — this is the marquee mapping the judges will check.
- **For PII / PHI / PCI:** the most accurate ATLAS technique is **AML.T0057** (LLM Data Leakage). If a more specific child sub-technique exists at implementation time (atlas.mitre.org has been evolving rapidly through 2026), use it.
- **For Code Detection:** **AML.T0050** (Command and Scripting Interpreter via LLM) is the closest fit.
- **For Hate Speech / Harassment / Violence / Sexual Content / Social Division / Profanity:** these aren't first-class ATLAS techniques but pivot via **AML.T0048** (External Harms) family — use the most-specific child available.
- Do NOT modify any other story's saved search. Story-app-03 owns `aegis_verdict_ingest`; this story extends that single search with a `lookup` clause only.
- The lookup is **enrichment**, not classification. The classifier remains Cisco AI Defense (per ADR-003). The ATLAS mapping is a presentation-layer convenience for SOC analysts.

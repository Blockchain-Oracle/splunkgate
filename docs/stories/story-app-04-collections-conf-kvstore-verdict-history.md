# Story — collections.conf KV-store schema for splunkgate_verdict_history

**ID:** story-app-04-collections-conf-kvstore-verdict-history
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-01-app-conf-and-metadata-skeleton
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** compliance officer reviewing the audit trail during an examiner visit
**I want to** see every SplunkGate verdict (with retention metadata + jurisdictional_tag for HIPAA/PCI/FSI profiles) persisted in a queryable Splunk KV-store collection that survives index rotation
**So that** when SOC events age out of the hot/warm index, the verdict record + its provenance (rules triggered, severity, explanation, trace_id, profile context) is still recallable for 7+ year regulator-grade retention without rehydrating frozen buckets

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/splunkgate_app/default/collections.conf` — NEW — one stanza `[splunkgate_verdict_history]` defining the KV-store collection schema, one row per verdict. Fields: `_key` (string, format `trace_id#timestamp_epoch`), `_user` (string, owner), `last_update` (time), `trace_id` (string, UUID), `timestamp` (time), `agent_id` (string), `surface` (string, one of mw_model/mw_tool/mw_subagent/mcp_score/mcp_judge_tool/mcp_check_output/mcp_audit/defenseclaw), `verdict_label` (string, ALLOW/BLOCK/MODIFY/REVIEW), `severity` (string, NONE_SEVERITY/LOW/MEDIUM/HIGH), `severity_score` (number, 0-3), `rules` (string, comma-separated for KV-store flat shape), `classifications` (string, comma-separated), `explanation` (string, max 4000 chars), `latency_ms` (number), `jurisdictional_tag` (string, FSI/HIPAA/PUBSEC/PCI/NONE for profile-gated dashboards in story app-07), `retention_until` (time, computed at insert: `now() + retention_years * 31536000s`, retention_years from profile lookup). Plus a `[splunkgate_profile_index]` collection (small lookup-style KV-store) mapping `jurisdictional_tag` → `retention_years`, `applicable_regs`, used by the Regulator Evidence Pack dashboard.
- `splunk_apps/splunkgate_app/default/transforms.conf` — UPDATE — append two lookup definitions: `[splunkgate_verdict_history_lookup]` (`external_type = kvstore`, `collection = splunkgate_verdict_history`, `fields_list = _key, _user, last_update, trace_id, timestamp, agent_id, surface, verdict_label, severity, severity_score, rules, classifications, explanation, latency_ms, jurisdictional_tag, retention_until`) and `[splunkgate_profile_index_lookup]` (`external_type = kvstore`, `collection = splunkgate_profile_index`, `fields_list = _key, jurisdictional_tag, retention_years, applicable_regs`). Mirrors DNS Guard's `transforms.conf` lookup-stanza pattern (`../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/transforms.conf`).
- `splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv` — NEW — 4-row seed CSV bootstrapping the `splunkgate_profile_index` KV-store on first install (jurisdictional_tag, retention_years, applicable_regs): `FSI,7,"FFIEC-AIML;SR-26-2"`, `HIPAA,7,"HIPAA-SafeHarbor-18"`, `PUBSEC,3,"NIST-AI-RMF"`, `PCI,1,"PCI-DSS-11.x"`. Wired via a one-shot saved search (`[SplunkGate - Bootstrap profile index]` in savedsearches.conf — orchestrator agent may need to update story app-03 if not already there; if so, flag in PR for follow-up).

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/splunkgate_app/default/collections.conf exists
When  grep -cE "^\[(splunkgate_verdict_history|splunkgate_profile_index)\]$" runs
Then  count == 2

Given the [splunkgate_verdict_history] stanza
When  grep "^field\." against it runs
Then  count >= 14 (all required fields declared with types)

Given the [splunkgate_verdict_history] stanza
When  grep "field.jurisdictional_tag = string\|field.retention_until = time" runs
Then  both lines present

Given the [splunkgate_verdict_history] stanza
When  grep "field.trace_id = string\|field.timestamp = time\|field.severity_score = number\|field.latency_ms = number" runs
Then  all four lines present

Given splunk_apps/splunkgate_app/default/transforms.conf has the lookup stanzas appended
When  grep -cE "^\[splunkgate_(verdict_history|profile_index)_lookup\]$" runs
Then  count == 2

Given the [splunkgate_verdict_history_lookup] stanza
When  grep "external_type = kvstore\|collection = splunkgate_verdict_history" runs
Then  both lines present

Given splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv exists
When  wc -l runs against it
Then  output is 5 (header + 4 data rows)

Given splunkgate_profile_seed.csv
When  grep -cE "^(FSI|HIPAA|PUBSEC|PCI)," runs
Then  count == 4 (all four profile rows present)

Given a Splunk container with splunkgate_app installed
When  the SPL "| inputlookup splunkgate_verdict_history_lookup | head 1" runs
Then  exit code is 0 (the KV-store collection exists and is readable)

Given splunk-appinspect runs against splunk_apps/splunkgate_app/
When  the output is parsed
Then  zero "error"-severity findings against tags collections_conf_valid, kvstore_collection_well_formed
```

---

## Shell verification

```bash
set -euo pipefail

# 1. Files exist
test -f splunk_apps/splunkgate_app/default/collections.conf
test -f splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv

# 2. Collections.conf has both stanzas
grep -q '^\[splunkgate_verdict_history\]$' splunk_apps/splunkgate_app/default/collections.conf
grep -q '^\[splunkgate_profile_index\]$' splunk_apps/splunkgate_app/default/collections.conf

# 3. splunkgate_verdict_history declares all required fields
for field in '_key = string' '_user = string' 'last_update = time' 'trace_id = string' \
             'timestamp = time' 'agent_id = string' 'surface = string' 'verdict_label = string' \
             'severity = string' 'severity_score = number' 'rules = string' 'classifications = string' \
             'explanation = string' 'latency_ms = number' 'jurisdictional_tag = string' 'retention_until = time'; do
  grep -q "^field\.${field}$" splunk_apps/splunkgate_app/default/collections.conf || \
    { echo "Missing field: $field"; exit 1; }
done

# 4. splunkgate_profile_index has its fields
for field in 'jurisdictional_tag = string' 'retention_years = number' 'applicable_regs = string'; do
  grep -q "^field\.${field}$" splunk_apps/splunkgate_app/default/collections.conf
done

# 5. Lookup stanzas appended to transforms.conf
grep -q '^\[splunkgate_verdict_history_lookup\]$' splunk_apps/splunkgate_app/default/transforms.conf
grep -q '^\[splunkgate_profile_index_lookup\]$' splunk_apps/splunkgate_app/default/transforms.conf
grep -A4 '^\[splunkgate_verdict_history_lookup\]$' splunk_apps/splunkgate_app/default/transforms.conf | grep -q 'external_type = kvstore'
grep -A4 '^\[splunkgate_verdict_history_lookup\]$' splunk_apps/splunkgate_app/default/transforms.conf | grep -q 'collection = splunkgate_verdict_history'

# 6. Seed CSV has correct row count and profile names
test "$(wc -l < splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv)" -eq 5
grep -q '^FSI,7,' splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv
grep -q '^HIPAA,7,' splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv
grep -q '^PUBSEC,3,' splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv
grep -q '^PCI,1,' splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv
head -1 splunk_apps/splunkgate_app/lookups/splunkgate_profile_seed.csv | grep -q '^jurisdictional_tag,retention_years,applicable_regs$'

# 7. Live KV-store readback (gated on SPLUNKGATE_SPLUNK_API_TOKEN)
if [ -n "${SPLUNKGATE_SPLUNK_API_TOKEN:-}" ]; then
  uv run python - <<'PY'
import splunklib.client as c, splunklib.results as r
svc = c.connect(host="${SPLUNKGATE_SPLUNK_HOST}", token="${SPLUNKGATE_SPLUNK_API_TOKEN}", app="splunkgate_app")
# Insert a synthetic row, read it back, delete
collection = svc.kvstore["splunkgate_verdict_history"]
key = collection.data.insert({"trace_id": "test-001", "agent_id": "ci-agent",
                              "surface": "mw_model", "verdict_label": "BLOCK",
                              "severity": "HIGH", "jurisdictional_tag": "FSI"})
rows = collection.data.query()
assert len(rows) >= 1
collection.data.delete_by_id(key["_key"])
print(f"KV-store roundtrip OK; inserted+deleted key {key['_key']}")
PY
fi

# 8. AppInspect
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

# 9. 400-LOC sanity
test "$(wc -l < splunk_apps/splunkgate_app/default/collections.conf)" -le 400
```

All nine blocks must exit 0 before opening the PR (block 7 gated on env var).

---

## Notes for coding agent

- Per `docs/architecture.md` § "Repo structure > splunk_apps/splunkgate_app/", `collections.conf` defines KV-store schemas; `lookups/*.csv` provides bootstrap seed rows; lookups defined via `transforms.conf` `[<name>_lookup]` stanzas with `external_type = kvstore`. Mirrors DNS Guard's exact wiring.
- Per `../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/collections.conf`, KV-store field types are: `string`, `number`, `bool`, `time`. No nested types — multi-value fields must be flattened to comma-separated strings at insert time. That's why `rules` and `classifications` are declared as `string` even though they're logically arrays.
- Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, the lookups directory must be at `splunk_apps/splunkgate_app/lookups/` (not under `default/`). Splunkbase rejects packages with lookups misplaced.
- The `jurisdictional_tag` field is the gating mechanism for the profile-conditional panels in dashboard 3 (story app-07): HIPAA Safe Harbor 18 panel only renders when `jurisdictional_tag=HIPAA`, PCI DSS 11.x panel only when `jurisdictional_tag=PCI`. The seed CSV bootstraps the four supported profiles per `docs/architecture.md` § "Profiles".
- Retention years per profile come from regulatory baselines: HIPAA 6 years minimum but we standardize 7 to align with FSI/SR-26-2 per `../../../context/03-regulatory/05-hipaa-healthcare-ai.md` + `../../../context/03-regulatory/03-ffiec-occ-fed-banking.md`; PUBSEC 3 years per NIST AI RMF guidance in `../../../context/03-regulatory/01-nist-ai-rmf.md`; PCI 1 year per `../../../context/03-regulatory/06-pci-dss-4-0-and-ai.md`.
- The `retention_until` field is computed at insert time, not query time — that way frozen-bucket purging policy can use a simple `| where retention_until < now() | outputlookup ...` to expire rows. Story app-08 (or a future ops story) handles the actual purging schedule.
- DNS Guard uses `_key = domain#anomalous_type` as the dedupe key. SplunkGate uses `_key = trace_id#timestamp_epoch` — same composite-key pattern, ensures one row per verdict event even if the saved search runs twice.
- The `[splunkgate_profile_index]` collection is intentionally small (4 rows) — it's a lookup table, not a metrics store. KV-store handles small lookup tables faster than CSV lookups because it doesn't lock the file during reads.
- Do NOT use the `replicate = true` flag — that's for distributed-search clusters and breaks AppInspect's single-instance check. KV-store collections in Splunk Cloud are automatically replicated by the platform.
- Per `../../../context/05-splunk-core/05-spl-reference.md`, `outputlookup append=true <name>` adds rows without rewriting the collection. `update_verdict_history` macro in story app-03 uses this exact pattern.
- If the `[SplunkGate - Bootstrap profile index]` saved search isn't already in story app-03's savedsearches.conf, do NOT add it here — flag in the PR description for story app-03 to add. This story owns the schema, not the bootstrapping; cross-story changes need explicit re-scoping per the file modification map rule.
- The 4000-char limit on `explanation` is a Splunk KV-store practical limit — longer Foundation-Sec explanations get truncated at insert time by the `update_verdict_history` macro (story app-03). Document this in the field comment.

# Story — props.conf + transforms.conf for cisco_ai_defense:aegis_verdict sourcetype

**ID:** story-app-02-props-transforms-for-aegis-verdict-sourcetype
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-01-app-conf-and-metadata-skeleton, story-core-02-otel-evaluation-event-emitter
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** SOC analyst running an SPL search across the Cisco Security Cloud sourcetype family
**I want to** type `index=main sourcetype="cisco_ai_defense:aegis_verdict"` and get fully field-extracted events with discoverable fields (verdict_label, severity, rules, explanation, trace_id, agent_id, surface, latency_ms)
**So that** downstream dashboards (stories app-05/06/07) and ES Risk-Based Alerting (story app-08) can search Aegis verdicts the same way they search any other Cisco AI Defense event, without per-dashboard regex hacks

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/default/props.conf` — NEW — one `[cisco_ai_defense:aegis_verdict]` stanza configuring JSON ingestion (`INDEXED_EXTRACTIONS = json`, `KV_MODE = none`, `LINE_BREAKER = ([\r\n]+)`, `NO_BINARY_CHECK = true`, `TIMESTAMP_FIELDS = timestamp`, `DATETIME_CONFIG = `, `category = Structured`, `pulldown_type = true`, `disabled = false`). Adds `EVAL-*` and `FIELDALIAS-*` lines that lift OTel `gen_ai.evaluation.*` attributes onto top-level fields and pull `aegis.surface`, `aegis.rules`, `aegis.trace_id` per OTel emission shape in `docs/architecture.md` § "OTel emission shape". Mirrors DNS Guard's `synthetic-data` stanza pattern verbatim (`../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/props.conf`).
- `splunk_apps/aegis_app/default/transforms.conf` — NEW — named field-extraction transforms referenced from props.conf when JSON-mode auto-extraction is insufficient. Two stanzas: `[aegis_rules_mv]` (mvexpand-friendly extraction of the `rules[]` array into a multi-value `rule` field) and `[aegis_severity_score]` (lookup-style mapping from severity string to a numeric `severity_score` for sorting + RBA integration in story-app-08).
- `splunk_apps/aegis_app/default/eventtypes.conf` — NEW — three eventtypes: `[aegis_verdict_all]` (`search = sourcetype="cisco_ai_defense:aegis_verdict"`), `[aegis_verdict_block]` (`search = sourcetype="cisco_ai_defense:aegis_verdict" verdict_label=BLOCK`), `[aegis_verdict_high_severity]` (`search = sourcetype="cisco_ai_defense:aegis_verdict" severity=HIGH`). Used by dashboards as canonical search fragments and by ES correlation searches.
- `splunk_apps/aegis_app/default/tags.conf` — NEW — tag bindings: `eventtype=aegis_verdict_all : tag=aegis, tag=ai_safety, tag=cisco_ai_defense_family`; `eventtype=aegis_verdict_block : tag=blocked`; `eventtype=aegis_verdict_high_severity : tag=critical`. Enables CIM-style tag searches.

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/default/props.conf exists
When  grep -c "^\[cisco_ai_defense:aegis_verdict\]" runs against it
Then  count == 1

Given props.conf [cisco_ai_defense:aegis_verdict] stanza is parsed
When  grep "^INDEXED_EXTRACTIONS = json$\|^KV_MODE = none$\|^TIMESTAMP_FIELDS = timestamp$\|^LINE_BREAKER = " runs
Then  all four lines are present

Given props.conf is parsed
When  grep -c "^EVAL-\|^FIELDALIAS-" runs
Then  count >= 6 (verdict_label, severity, rules, explanation, trace_id, agent_id, surface, latency_ms — at least 6 aliases/evals total)

Given splunk_apps/aegis_app/default/transforms.conf exists
When  grep -cE "^\[aegis_rules_mv\]|^\[aegis_severity_score\]" runs
Then  count == 2

Given splunk_apps/aegis_app/default/eventtypes.conf exists
When  grep -cE "^\[aegis_verdict_(all|block|high_severity)\]" runs
Then  count == 3

Given splunk_apps/aegis_app/default/tags.conf exists
When  grep -c "^tag = aegis$\|^tag = ai_safety$\|^tag = cisco_ai_defense_family$" runs
Then  count >= 3

Given a sample OTel-shape JSON event is piped to Splunk via splunk-sdk-python (or curl into HEC) using sourcetype cisco_ai_defense:aegis_verdict
When  the search "search sourcetype=cisco_ai_defense:aegis_verdict | head 1" runs against Splunk Cloud
Then  the result has fields: verdict_label, severity, rules, explanation, trace_id, agent_id, surface, latency_ms (verified via `eventcount` + `| fields *` inspection)

Given splunk-appinspect inspect runs against splunk_apps/aegis_app/
When  the output is parsed
Then  zero "error"-severity findings against tags props_conf_no_invalid_stanzas, transforms_conf_valid_lookups, eventtypes_conf_valid
```

---

## Shell verification

```bash
set -euo pipefail

# 1. Files exist with required stanzas
test -f splunk_apps/aegis_app/default/props.conf
test -f splunk_apps/aegis_app/default/transforms.conf
test -f splunk_apps/aegis_app/default/eventtypes.conf
test -f splunk_apps/aegis_app/default/tags.conf

grep -q '^\[cisco_ai_defense:aegis_verdict\]$' splunk_apps/aegis_app/default/props.conf
grep -q '^INDEXED_EXTRACTIONS = json$' splunk_apps/aegis_app/default/props.conf
grep -q '^KV_MODE = none$' splunk_apps/aegis_app/default/props.conf
grep -q '^TIMESTAMP_FIELDS = timestamp$' splunk_apps/aegis_app/default/props.conf
grep -q '^LINE_BREAKER = ' splunk_apps/aegis_app/default/props.conf

# 2. At least 6 EVAL/FIELDALIAS lines lifting OTel attrs to top-level fields
test "$(grep -cE '^(EVAL|FIELDALIAS)-' splunk_apps/aegis_app/default/props.conf)" -ge 6

# 3. transforms.conf has the two required stanzas
grep -q '^\[aegis_rules_mv\]$' splunk_apps/aegis_app/default/transforms.conf
grep -q '^\[aegis_severity_score\]$' splunk_apps/aegis_app/default/transforms.conf

# 4. eventtypes + tags
for et in aegis_verdict_all aegis_verdict_block aegis_verdict_high_severity; do
  grep -q "^\[${et}\]$" splunk_apps/aegis_app/default/eventtypes.conf
done
grep -q 'aegis' splunk_apps/aegis_app/default/tags.conf
grep -q 'cisco_ai_defense_family' splunk_apps/aegis_app/default/tags.conf

# 5. Round-trip via local Splunk container (gated by AEGIS_SPLUNK_HEC_TOKEN)
if [ -n "${AEGIS_SPLUNK_HEC_TOKEN:-}" ]; then
  uv run python scripts/emit_sample_verdict.py | \
    curl -k -H "Authorization: Splunk ${AEGIS_SPLUNK_HEC_TOKEN}" \
      -d @- "${AEGIS_SPLUNK_HEC_URL}/services/collector/event"
  sleep 5  # indexer lag
  uv run python -c "
import splunklib.client as c, splunklib.results as r
svc = c.connect(host='${AEGIS_SPLUNK_HOST}', token='${AEGIS_SPLUNK_API_TOKEN}')
job = svc.jobs.create('search sourcetype=cisco_ai_defense:aegis_verdict | head 1 | fields verdict_label severity trace_id agent_id surface latency_ms', earliest_time='-5m')
while not job.is_done(): pass
for row in r.JSONResultsReader(job.results(output_mode='json')):
    assert all(f in row for f in ('verdict_label','severity','trace_id','agent_id','surface','latency_ms')), row
"
fi

# 6. AppInspect
uv run splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud \
  --output-file appinspect-report.json --data-format json
python - <<'PY'
import json, sys
r = json.load(open("appinspect-report.json"))
errors = [c for rep in r.get("reports", []) for g in rep.get("groups", []) for c in g.get("checks", []) if c.get("result") == "error"]
print(f"Errors: {len(errors)}")
if errors:
    for e in errors: print(" -", e.get("name"), e.get("messages"))
    sys.exit(1)
PY

# 7. 400-LOC sanity
for f in splunk_apps/aegis_app/default/props.conf splunk_apps/aegis_app/default/transforms.conf splunk_apps/aegis_app/default/eventtypes.conf splunk_apps/aegis_app/default/tags.conf; do
  test "$(wc -l < "$f")" -le 400
done
```

All seven blocks must exit 0 before opening the PR (block 5 is conditional on env vars; otherwise skipped).

---

## Notes for coding agent

- Per `docs/architecture.md` § "ADR-005: Aegis events emit to `cisco_ai_defense:aegis_verdict` sourcetype" — colocates with Cisco Security Cloud app 7404 v3.6.6 (Cisco Systems, 55K installs) `cisco_ai_defense:*` sourcetype family. Verified live via Abu's Splunk Cloud instance per `../../../context/sources/docs-saved/splunk-cloud-live-verification-2026-06-02.md`.
- Per `docs/architecture.md` § "OTel emission shape", every verdict event arrives as JSON with these attributes at the top level: `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`, `mcp.method.name`, `mcp.session.id`, `aegis.surface`, `aegis.rules` (array), `aegis.trace_id`. Use `FIELDALIAS-*` lines to map these dotted-attribute names to flat field names dashboards consume (`verdict_label = gen_ai.evaluation.score.label`, etc.).
- Per `../../../context/05-splunk-core/05-spl-reference.md`, `FIELDALIAS-x = source AS target` is the canonical mechanism for renaming JSON-extracted dotted-name fields into flat top-level fields. `EVAL-x = field = expression` is for computed values (e.g., `EVAL-severity_score = case(severity=="HIGH", 3, severity=="MEDIUM", 2, severity=="LOW", 1, true(), 0)`).
- Per DNS Guard's `props.conf` (`../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/props.conf`), the canonical JSON-ingest pattern is exactly: `INDEXED_EXTRACTIONS = json; KV_MODE = none; LINE_BREAKER = ([\r\n]+); NO_BINARY_CHECK = true; TIMESTAMP_FIELDS = timestamp; category = Structured; pulldown_type = true`. Replicate verbatim with the sourcetype name swapped to `cisco_ai_defense:aegis_verdict`.
- `KV_MODE = none` matters: without it, Splunk runs auto-KV extraction on top of JSON-indexed extractions, doubling field counts and breaking dashboards that expect unique field names. Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`.
- The `rules` array field needs special handling because OTel sends `aegis.rules = ["Prompt Injection", "PII"]` (JSON array). Splunk's JSON ingest auto-creates `aegis.rules{}` multi-value field; use `FIELDALIAS-rule = 'aegis.rules{}' AS rule` to flatten. The dashboards then can `mvexpand rule` to do per-rule heatmaps (story app-05).
- The `[aegis_severity_score]` transform is referenced by ES RBA in story app-08; pre-computing the score at index time (via `EVAL-severity_score = ...` in props.conf) is sufficient and avoids per-search overhead. Leave the named transform stub in transforms.conf for forward-compat — ES RBA can call into it directly via `lookup` if a future story moves to explicit lookup-driven scoring.
- `eventtypes.conf` triggers from sourcetype only (not from index) so the dashboards work whether the deployment routes Aegis events to `main`, `cisco_ai_defense`, or a dedicated `aegis` index. Sourcetype is the stable anchor.
- The `tags.conf` `cisco_ai_defense_family` tag is what lets SOC analysts run unified searches like `tag=cisco_ai_defense_family severity=HIGH` across Cisco AI Defense + Aegis events. This is the "colocate for unified SOC search" claim from `docs/architecture.md` ADR-005.
- Do NOT add `DELIMS`, `EXTRACT-`, or regex-based extractions to props.conf — JSON indexed-extractions handles all the lifting. Adding regex on top makes the conf file twice as long and slower at search time.
- Sample event for round-trip testing should match the exact shape emitted by `aegis_core.otel.emit_event()` (story-core-02). The `scripts/emit_sample_verdict.py` referenced in shell block 5 lives outside this story's file modification map; if it doesn't exist yet, gate the block on `[ -f scripts/emit_sample_verdict.py ]`.

# Story — risk_factors.conf for ES Risk-Based Alerting integration

**ID:** story-app-08-risk-factors-conf-es-rba-integration
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-03-savedsearches-and-mltk-macros
**Estimate:** ~1h
**Status:** PENDING

---

## User story

**As a** Splunk Enterprise Security (ES) admin running Risk-Based Alerting
**I want to** see SplunkGate verdict severity automatically map to ES risk-score buckets (HIGH → 80, MEDIUM → 50, LOW → 20, NONE_SEVERITY → 0), so HIGH-severity verdicts generate ES notable events tagged on `agent_id` as the risk object
**So that** the SOC's existing RBA workflow surfaces agent-safety risk alongside endpoint/network risk without rebuilding correlation searches from scratch, and high-risk agents trigger ES notables that map directly to MITRE ATLAS adversarial-ML tactics

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/splunkgate_app/default/risk_factors.conf` — NEW — Risk factor stanzas mapping each AI Defense rule classification to an ES risk score. Required stanzas (mirroring DNS Guard's `risk_factors.conf` shape verbatim — `../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/risk_factors.conf`), one per verbatim Cisco AI Defense rule name from `../../../context/07-cisco-stack/01-ai-defense-deep.md`: `[SplunkGate - Code Detection]`, `[SplunkGate - Harassment]`, `[SplunkGate - Hate Speech]`, `[SplunkGate - PCI]`, `[SplunkGate - PHI]`, `[SplunkGate - PII]`, `[SplunkGate - Prompt Injection]`, `[SplunkGate - Profanity]`, `[SplunkGate - Sexual Content & Exploitation]`, `[SplunkGate - Social Division & Polarization]`, `[SplunkGate - Violence & Public Safety Threats]` (11 stanzas, one per Cisco AI Defense rule — earlier drafts used hallucinated names like `Toxicity`, `Self-Harm`, bare `Violence` which DO NOT exist in the AI Defense API). Each stanza has: `conditions = [{"comparator":"equal","field":"rule","value":"<rule name>","value_type":"value"}]`, `description = <one-line>`, `value = <score based on severity tier>`, `disabled = 0`. Plus one severity-based multiplier stanza `[SplunkGate - HIGH severity multiplier]` (`operation_group = mult`, `value = 2`) that doubles risk score when `severity=HIGH`. Plus an exclusion stanza `[SplunkGate - Whitelisted agent]` (mirrors DNS Guard's `[DNS Guard AI - Whitelist]`) that zeroes risk for any agent in a whitelist lookup.
- `splunk_apps/splunkgate_app/default/savedsearches.conf` — UPDATE — append the ES RBA correlation alert wiring to the existing `[SplunkGate - HIGH severity correlation alert]` stanza (added in story app-03): `action.risk.param._risk_object = agent_id`, `action.risk.param._risk_object_type = system`, `action.risk.param._risk_score = 80`, `action.risk.param.verbose = 0`, `action.risk.forceCsvResults = 1`, `action.notable.param.rule_title = "SplunkGate HIGH severity verdict on agent $result.agent_id$"`, `action.notable.param.rule_description = "SplunkGate classified verdict as HIGH severity. Rules: $result.rules$. Surface: $result.surface$. Trace: $result.trace_id$."`, `action.notable.param.security_domain = threat`, `action.notable.param.severity = high`. Mirrors DNS Guard's `[Threat - DNSGuardAI - Global Alert]` ES wiring (action.risk + action.risk.param.*).
- `splunk_apps/splunkgate_app/lookups/splunkgate_whitelist_agent.csv` — NEW — 2-row seed CSV (header + 1 example): `agent_id,reason` / `ci-smoke-agent,"Used by SplunkGate CI for smoke tests; safe to ignore in production RBA"`. Provides the whitelist mechanism referenced by `[SplunkGate - Whitelisted agent]` risk factor. Wired via a transforms.conf `[splunkgate_whitelist_agent_lookup]` stanza (UPDATE).
- `splunk_apps/splunkgate_app/default/transforms.conf` — UPDATE — append `[splunkgate_whitelist_agent_lookup]` (`filename = splunkgate_whitelist_agent.csv`, `external_type = csv`, `fields_list = agent_id, reason`).

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/splunkgate_app/default/risk_factors.conf exists
When  grep -cE "^\[SplunkGate - " runs
Then  count >= 12 (11 rule stanzas + 1 multiplier + 1 whitelist exclusion = 13 minimum)

Given risk_factors.conf is parsed
When  grep -E "^\[SplunkGate - (Code Detection|Harassment|Hate Speech|PCI|PHI|PII|Prompt Injection|Profanity|Sexual Content & Exploitation|Social Division & Polarization|Violence & Public Safety Threats)\]" runs
Then  count == 11 (all 11 Cisco AI Defense rule classifications represented)

Given risk_factors.conf [SplunkGate - HIGH severity multiplier] stanza
When  grep "operation_group = mult\|value = 2" runs
Then  both lines present

Given risk_factors.conf [SplunkGate - Whitelisted agent] stanza
When  grep "operation_group = mult\|value = 0" runs
Then  both lines present

Given each rule risk-factor stanza has a "conditions = ..." line
When  the JSON is parsed
Then  the conditions array contains exactly one comparator with field="rule" and value=<rule name>

Given splunk_apps/splunkgate_app/default/savedsearches.conf [SplunkGate - HIGH severity correlation alert] stanza
When  grep "action.risk = 1\|action.risk.param._risk_object = agent_id\|action.notable.param.security_domain = threat\|action.notable.param.severity = high" runs
Then  all four lines present

Given splunk_apps/splunkgate_app/lookups/splunkgate_whitelist_agent.csv exists
When  head -1 runs
Then  output is "agent_id,reason"

Given splunk_apps/splunkgate_app/default/transforms.conf [splunkgate_whitelist_agent_lookup] stanza
When  grep "filename = splunkgate_whitelist_agent.csv\|external_type = csv" runs
Then  both lines present

Given a Splunk Cloud instance with ES installed and the app loaded
When  the SPL "| inputlookup risk_factors_lookup search SplunkGate" runs (ES synthesizes this lookup from risk_factors.conf at install time)
Then  ≥ 11 rows return with field "name" matching "SplunkGate - *"

Given splunk-appinspect runs against splunk_apps/splunkgate_app/
When  the output is parsed
Then  zero "error"-severity findings against tags risk_factors_conf_valid, savedsearches_es_actions_valid

Given a synthetic HIGH-severity verdict event flows through Splunk
When  the [SplunkGate - HIGH severity correlation alert] saved search fires
Then  an entry appears in `risk_index=risk` with risk_object=agent_id, risk_object_type=system, risk_score >= 80
```

---

## Shell verification

```bash
set -euo pipefail

# 1. Files exist
test -f splunk_apps/splunkgate_app/default/risk_factors.conf
test -f splunk_apps/splunkgate_app/lookups/splunkgate_whitelist_agent.csv

# 2. Risk factor stanzas — 11 rule stanzas
test "$(grep -cE '^\[SplunkGate - (Code Detection|Harassment|Hate Speech|PCI|PHI|PII|Prompt Injection|Profanity|Sexual Content & Exploitation|Social Division & Polarization|Violence & Public Safety Threats)\]$' splunk_apps/splunkgate_app/default/risk_factors.conf)" -eq 11

# 3. HIGH severity multiplier + whitelist exclusion
grep -q '^\[SplunkGate - HIGH severity multiplier\]$' splunk_apps/splunkgate_app/default/risk_factors.conf
grep -q '^\[SplunkGate - Whitelisted agent\]$' splunk_apps/splunkgate_app/default/risk_factors.conf
awk '/^\[SplunkGate - HIGH severity multiplier\]/,/^\[/' splunk_apps/splunkgate_app/default/risk_factors.conf | grep -q '^operation_group = mult$'
awk '/^\[SplunkGate - HIGH severity multiplier\]/,/^\[/' splunk_apps/splunkgate_app/default/risk_factors.conf | grep -q '^value = 2$'
awk '/^\[SplunkGate - Whitelisted agent\]/,/^\[/' splunk_apps/splunkgate_app/default/risk_factors.conf | grep -q '^operation_group = mult$'
awk '/^\[SplunkGate - Whitelisted agent\]/,/^\[/' splunk_apps/splunkgate_app/default/risk_factors.conf | grep -q '^value = 0$'

# 4. Every stanza has a description + a conditions line
test "$(grep -c '^description = ' splunk_apps/splunkgate_app/default/risk_factors.conf)" -ge 13
test "$(grep -c '^conditions = ' splunk_apps/splunkgate_app/default/risk_factors.conf)" -ge 11

# 5. Each conditions line is valid JSON
python - <<'PY'
import json, re, sys
with open("splunk_apps/splunkgate_app/default/risk_factors.conf") as f:
    text = f.read()
matches = re.findall(r'^conditions = (.+)$', text, re.MULTILINE)
assert len(matches) >= 11, f"Expected >= 11 conditions, got {len(matches)}"
for m in matches:
    parsed = json.loads(m)
    assert isinstance(parsed, list), f"conditions must be list: {m}"
    assert len(parsed) >= 1
print(f"All {len(matches)} conditions parse as JSON.")
PY

# 6. ES correlation alert wired in savedsearches.conf
awk '/^\[SplunkGate - HIGH severity correlation alert\]/,/^\[/' splunk_apps/splunkgate_app/default/savedsearches.conf | grep -q '^action.risk = 1$'
awk '/^\[SplunkGate - HIGH severity correlation alert\]/,/^\[/' splunk_apps/splunkgate_app/default/savedsearches.conf | grep -q '^action.risk.param._risk_object = agent_id$'
awk '/^\[SplunkGate - HIGH severity correlation alert\]/,/^\[/' splunk_apps/splunkgate_app/default/savedsearches.conf | grep -q '^action.notable.param.security_domain = threat$'
awk '/^\[SplunkGate - HIGH severity correlation alert\]/,/^\[/' splunk_apps/splunkgate_app/default/savedsearches.conf | grep -q '^action.notable.param.severity = high$'

# 7. Whitelist CSV + lookup stanza
head -1 splunk_apps/splunkgate_app/lookups/splunkgate_whitelist_agent.csv | grep -q '^agent_id,reason$'
grep -q '^\[splunkgate_whitelist_agent_lookup\]$' splunk_apps/splunkgate_app/default/transforms.conf
awk '/^\[splunkgate_whitelist_agent_lookup\]/,/^\[/' splunk_apps/splunkgate_app/default/transforms.conf | grep -q '^filename = splunkgate_whitelist_agent.csv$'
awk '/^\[splunkgate_whitelist_agent_lookup\]/,/^\[/' splunk_apps/splunkgate_app/default/transforms.conf | grep -q '^external_type = csv$'

# 8. Live ES integration round-trip (gated on SPLUNKGATE_SPLUNK_API_TOKEN + ES installed)
if [ -n "${SPLUNKGATE_SPLUNK_API_TOKEN:-}" ] && [ -n "${SPLUNKGATE_ES_INSTALLED:-}" ]; then
  uv run python - <<'PY'
import splunklib.client as c, splunklib.results as r, time
svc = c.connect(host="${SPLUNKGATE_SPLUNK_HOST}", token="${SPLUNKGATE_SPLUNK_API_TOKEN}", app="splunkgate_app")
# Push a synthetic HIGH verdict, run the correlation search, check risk index
svc.indexes["main"].submit('{"timestamp": ' + str(int(time.time())) +
    ', "verdict_label": "BLOCK", "severity": "HIGH", "agent_id": "test-rba-agent",'
    + ' "rule": "Prompt Injection", "surface": "mw_model", "trace_id": "test-uuid", "latency_ms": 12.0}',
    sourcetype="cisco_ai_defense:splunkgate_verdict")
time.sleep(10)
job = svc.saved_searches["SplunkGate - HIGH severity correlation alert"].dispatch()
while not job.is_done(): time.sleep(1)
time.sleep(5)
risk_job = svc.jobs.create('search index=risk source="SplunkGate - HIGH severity correlation alert" earliest=-5m | head 1')
while not risk_job.is_done(): time.sleep(1)
rows = list(r.JSONResultsReader(risk_job.results(output_mode="json")))
assert len(rows) >= 1, "No risk event generated"
assert float(rows[0].get("risk_score", 0)) >= 80, f"Risk score too low: {rows[0]}"
print(f"RBA integration OK; risk_score={rows[0]['risk_score']}")
PY
fi

# 9. AppInspect
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

# 10. 400-LOC sanity
test "$(wc -l < splunk_apps/splunkgate_app/default/risk_factors.conf)" -le 400
```

All ten blocks must exit 0 before opening the PR (block 8 gated on env vars).

---

## Notes for coding agent

- Per `../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/risk_factors.conf`, the canonical Splunk ES risk-factor stanza shape is: `[name]` + `conditions = [{"comparator":"equal","field":"<field>","value":"<value>","value_type":"value"}]` + `description = <one-line>` + `value = <integer>` + `disabled = 0`. Mirror this verbatim with field=`rule`.
- Per `../../../context/05-splunk-core/01-enterprise-security-architecture.md`, ES Risk-Based Alerting reads `risk_factors.conf` at install time and synthesizes a `risk_factors_lookup` collection. Correlation searches use `action.risk = 1` + `action.risk.param.*` keys to write to the `risk` index; ES then surfaces HIGH-cumulative-risk objects as notable events.
- Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, the 11 verbatim Cisco AI Defense rule classifications are: **Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats**. Each gets its own risk-factor stanza. Per-rule risk values: Code Detection 40, Harassment 50, Hate Speech 50, PCI 70, PHI 70, PII 50, Prompt Injection 60, Profanity 20, Sexual Content & Exploitation 60, Social Division & Polarization 40, Violence & Public Safety Threats 70. (Higher = more SOC priority; PHI/PCI/Violence&PublicSafetyThreats at 70 because they trigger regulatory escalation.) Earlier drafts used hallucinated names (`Toxicity`, `Self-Harm`, bare `Violence`) — DO NOT use these; the AI Defense API returns events with the verbatim names only.
- Per `../inspiration/Splunk-DNS-Guard-AI/Splunk-DNS-Guard-AI/default/risk_factors.conf`, the `operation_group = mult` pattern is how Splunk multiplies (rather than adds) risk values when conditions match. DNS Guard's whitelist uses `operation_group = mult, value = 0` to zero out matched events. SplunkGate's HIGH multiplier uses `mult, value = 2` to double; SplunkGate's whitelist uses `mult, value = 0` to zero — exact same idiom.
- The `[SplunkGate - HIGH severity correlation alert]` saved search in story app-03 is the trigger; this story wires it to ES RBA. Verify story-app-03 already added `action.risk = 1` + `action.notable.param.verbose = 0` placeholders — if not, this story's PR description must call out the cross-story change.
- The `_risk_object = agent_id` choice (not `trace_id` or `surface`) is deliberate: ES RBA aggregates risk per object over time. Aggregating per agent_id surfaces "agent X is accumulating risk across many sessions" which is the SOC-actionable insight; aggregating per trace_id would scatter risk and miss patterns.
- The `_risk_object_type = system` tag puts SplunkGate agents in the same RBA bucket as endpoints/servers, alongside the existing CIM `system` type. Other valid types are `user`, `network_artifacts`, `endpoint` — `system` is the closest semantic match for an autonomous AI agent.
- The whitelist CSV's `ci-smoke-agent` row is required so CI runs don't inflate production RBA. Document in the README that production deployments should clear this row before going live.
- ES installation is detected via `splunk-appinspect` — if ES is not present, the risk_factors.conf still parses cleanly but doesn't activate. Document in `splunk_apps/splunkgate_app/README` (story app-01) that ES is an optional dependency, but RBA features only activate when ES is present.
- Per `../../../context/05-splunk-core/01-enterprise-security-architecture.md` § "MITRE ATLAS mapping", ES correlation searches can include `action.notable.param.MITRE_ATLAS = <tactic_id>`. SplunkGate's HIGH-severity rule should set MITRE_ATLAS to the relevant adversarial-ML tactic (e.g., "AML.T0051" Prompt Injection, "AML.T0057" LLM Data Leakage). If the spec file `../../../context/sources/docs-saved/atlas-data-latest.yaml` has the current IDs, use those verbatim.
- The DNS Guard `value = 50` flat-rate-per-stanza is a fine starting point but SplunkGate tunes per-rule (40–70 range) because rule severity varies more in the AI-safety domain than in DNS-anomaly. The HIGH-severity multiplier (×2) is what produces RBA-priority HIGH scores (e.g., PHI base 70 × HIGH multiplier 2 = 140, well above ES's typical 100-point HIGH bucket).
- `disabled = 0` on every rule stanza means risk factors activate on install. The whitelist exclusion is also `disabled = 0` because Splunk evaluates it at search time per-event; CI smoke-test events get zeroed before they hit the risk index.
- If risk_factors.conf approaches 400 LOC, consolidate by using shorter descriptions (one short sentence each). Don't split across files — Splunk loads only `default/risk_factors.conf`, not includes.
- Per `docs/architecture.md` § "ADR-005", SplunkGate events live in the `cisco_ai_defense:splunkgate_verdict` sourcetype. Risk factors don't filter on sourcetype directly; they filter on the `rule` field which is extracted from the JSON event via props.conf (story app-02). The correlation search supplies the sourcetype constraint.

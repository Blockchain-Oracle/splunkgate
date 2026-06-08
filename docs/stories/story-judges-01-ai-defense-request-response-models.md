# Story — AI Defense Inspect request/response Pydantic v2 models

**ID:** story-judges-01-ai-defense-request-response-models
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** judgment-layer developer wiring SplunkGate to Cisco AI Defense
**I want to** have typed `InspectRequest` and `InspectResponse` Pydantic v2 models that mirror the documented Inspection API schema exactly (including the 11 canonical rules and the `rules` field name)
**So that** every other story in EPIC-04 can serialize / deserialize traffic without re-deriving the schema, and the type checker catches the historical `triggered_rules` hallucination at compile time

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/src/splunkgate_judges/__init__.py` — NEW — empty package marker with `__version__ = "0.1.0"`
- `packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py` — NEW — Pydantic v2 models: `AIDefenseRule` (StrEnum of the 11 rules verbatim), `Classification` (StrEnum: SECURITY_VIOLATION, PRIVACY_VIOLATION, SAFETY_VIOLATION, RELEVANCE_VIOLATION), `InspectMessage`, `InspectConfig`, `InspectRequest`, `RuleHit` (rule_name + classification + entity_types), `InspectResponse`
- `packages/splunkgate_judges/src/splunkgate_judges/py.typed` — NEW — marker file for PEP 561
- `packages/splunkgate_judges/pyproject.toml` — NEW — workspace member declaring deps on `splunkgate-core`, `pydantic>=2`
- `packages/splunkgate_judges/tests/__init__.py` — NEW — empty
- `packages/splunkgate_judges/tests/test_ai_defense_types.py` — NEW — ≥ 12 behavioral tests covering: all 11 rule names enumerated, severity includes NONE_SEVERITY, response field is `rules` not `triggered_rules`, classifications enum round-trip, JSON-Schema generation matches Cisco-documented shape, optional `metadata`/`config` round-trip, `attack_technique`/`event_id`/`client_transaction_id` optional fields

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py defines the AIDefenseRule enum
When  `python -c "from splunkgate_judges.ai_defense_types import AIDefenseRule; print(sorted(r.value for r in AIDefenseRule))"` runs
Then  the output contains exactly these 11 strings verbatim (sorted):
      "Code Detection","Harassment","Hate Speech","PCI","PHI","PII","Profanity","Prompt Injection","Sexual Content & Exploitation","Social Division & Polarization","Violence & Public Safety Threats"

Given the InspectResponse Pydantic model is defined
When  `python -c "from splunkgate_judges.ai_defense_types import InspectResponse; print('rules' in InspectResponse.model_fields and 'triggered_rules' not in InspectResponse.model_fields)"` runs
Then  the output is "True"

Given the Severity enum is exposed by splunkgate_judges.ai_defense_types
When  `python -c "from splunkgate_judges.ai_defense_types import Severity; print('NONE_SEVERITY' in [s.value for s in Severity])"` runs
Then  the output is "True"
And   the enum contains exactly {NONE_SEVERITY, LOW, MEDIUM, HIGH}

Given the test file packages/splunkgate_judges/tests/test_ai_defense_types.py exists
When  `uv run pytest packages/splunkgate_judges/tests/test_ai_defense_types.py -v` runs
Then  ≥ 12 tests pass and 0 fail

Given the package src tree
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py` runs
Then  exit code is 0

Given the package src tree
When  `find packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py -exec wc -l {} +` runs
Then  the line count is ≤ 400

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Models import + the 11 rules are enumerated verbatim
uv run python -c "
from splunkgate_judges.ai_defense_types import AIDefenseRule, InspectResponse, Severity
expected = {
    'Code Detection','Harassment','Hate Speech','PCI','PHI','PII',
    'Prompt Injection','Profanity','Sexual Content & Exploitation',
    'Social Division & Polarization','Violence & Public Safety Threats'
}
actual = {r.value for r in AIDefenseRule}
assert actual == expected, f'rule mismatch: {actual ^ expected}'
assert 'rules' in InspectResponse.model_fields
assert 'triggered_rules' not in InspectResponse.model_fields
assert 'NONE_SEVERITY' in {s.value for s in Severity}
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/splunkgate_judges/tests/test_ai_defense_types.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# Strict typecheck
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py
# Must exit 0

# 400-LOC cap
wc -l packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py | awk '{ if ($1 > 400) exit 1 }'
# Must exit 0

# §14 clean on production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, Cisco AI Defense Inspection API response field is `rules`, NOT `triggered_rules`.** Prior research called it `triggered_rules`; the actual API field is `rules`. The audit (`../../../context/HALLUCINATION-AUDIT.md`) logs this. Use `rules` and add a docstring comment citing the audit so future contributors do not regress.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md`, severity enum includes NONE_SEVERITY.** The four values are `NONE_SEVERITY`, `LOW`, `MEDIUM`, `HIGH`. Do not collapse `NONE_SEVERITY` to `None` — Cisco emits the literal string `"NONE_SEVERITY"`.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7**, the 11 canonical rule names are verbatim: Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats. Include the ampersands in `"Sexual Content & Exploitation"` and `"Violence & Public Safety Threats"` and the slash-free spacing in `"Social Division & Polarization"`.
- The DefenseClaw `internal/gateway/cisco_inspect.go` adds 3 extra rule names (Jailbreak, Sensitive Data, Data Leakage) — that contradiction is logged in `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7. This story uses the **public-docs 11** only. The DefenseClaw delta is handled in a later story.
- The Pydantic `Severity` enum here may overlap with `splunkgate_core.verdict.Severity` — import from `splunkgate_core` if it already exports `NONE_SEVERITY`, else define locally and add a TODO ADR to unify.
- Re-use `splunkgate_core.verdict.Severity` if it matches; otherwise define `Severity` here mirroring the AI Defense response.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free signup with US-corp email) is the demo-recording path — the model schema in this story is what the Explorer Edition responses validate against during the demo video.

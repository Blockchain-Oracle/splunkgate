# Story — AI Defense respx mock + env-var toggle + fixture matrix

**ID:** story-judges-04-ai-defense-mock-respx-fixtures
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-judges-01-ai-defense-request-response-models
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** developer running the full SplunkGate test suite without a Cisco AI Defense tenant
**I want to** flip `SPLUNKGATE_AI_DEFENSE_MOCK=1` and have the client return deterministic verdicts covering all 11 documented rules at every severity tier
**So that** CI, eval, and demo recordings run without paid Cisco credentials, while the same code path runs live against the Explorer Edition when the env var is unset

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/src/splunkgate_judges/ai_defense_mock.py` — NEW — `MockAIDefenseClient` class with the same async interface as `AIDefenseClient`; `inspect_chat(req)` dispatches to a deterministic verdict matrix keyed on `req.messages[-1].content`; supports respx-based wiring as `mock_router()` returning a `respx.Router` registering all 4 regional base URLs; exposes `FIXTURE_MATRIX: dict[str, InspectResponse]` covering the 11 rules × {NONE_SEVERITY, LOW, MEDIUM, HIGH} transitions (44 fixtures), plus a default `is_safe=True NONE_SEVERITY` response for unknown text
- `packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` — UPDATE — add `AIDefenseClient.from_env()` factory: reads `SPLUNKGATE_AI_DEFENSE_MOCK` (truthy → returns `MockAIDefenseClient`), else reads `SPLUNKGATE_AI_DEFENSE_API_KEY` (required when not mock), `SPLUNKGATE_AI_DEFENSE_REGION` (default `"us"`)
- `packages/splunkgate_judges/src/splunkgate_judges/_fixtures/__init__.py` — NEW — fixture loader
- `packages/splunkgate_judges/src/splunkgate_judges/_fixtures/ai_defense_matrix.json` — NEW — the 44-row fixture matrix as JSON (one row per rule × severity), exact `InspectResponse`-shaped payloads
- `packages/splunkgate_judges/tests/test_ai_defense_mock.py` — NEW — ≥ 14 tests: all 11 rules appear in matrix; all 4 severities appear; every fixture round-trips through `InspectResponse.model_validate`; `SPLUNKGATE_AI_DEFENSE_MOCK=1` causes `from_env()` to return a `MockAIDefenseClient`; unset `SPLUNKGATE_AI_DEFENSE_MOCK` with missing `SPLUNKGATE_AI_DEFENSE_API_KEY` raises `AIDefenseAuthError`; deterministic dispatch — same input string returns same response twice; default response is `is_safe=True, severity=NONE_SEVERITY`; respx-wired mock returns the matrix response for the matching trigger string
- `packages/splunkgate_judges/conftest.py` — NEW — exposes `ai_defense_mock` pytest fixture returning a `MockAIDefenseClient`; resets env vars between tests

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/splunkgate_judges/src/splunkgate_judges/_fixtures/ai_defense_matrix.json exists
When  `python -c "import json; m=json.load(open('packages/splunkgate_judges/src/splunkgate_judges/_fixtures/ai_defense_matrix.json')); print(len(m))"` runs
Then  the output is exactly "44"   # 11 rules × 4 severities

Given the matrix is loaded
When  the set of distinct rule_name values across all fixtures is computed
Then  it equals exactly the 11 documented rules (Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats)

Given the matrix is loaded
When  the set of distinct severity values is computed
Then  it equals exactly {"NONE_SEVERITY","LOW","MEDIUM","HIGH"}

Given SPLUNKGATE_AI_DEFENSE_MOCK=1 is set in the environment
When  AIDefenseClient.from_env() is called
Then  the returned object's class.__name__ is "MockAIDefenseClient"

Given SPLUNKGATE_AI_DEFENSE_MOCK is unset and SPLUNKGATE_AI_DEFENSE_API_KEY is unset
When  AIDefenseClient.from_env() is called
Then  AIDefenseAuthError is raised with message including "SPLUNKGATE_AI_DEFENSE_API_KEY"

Given the mock client is dispatched with the same trigger text twice
When  the two responses are compared
Then  they are byte-equal (deterministic dispatch)

Given the mock client receives text not matching any fixture trigger
When  inspect_chat is called
Then  the response is is_safe=True and severity=NONE_SEVERITY

Given `uv run pytest packages/splunkgate_judges/tests/test_ai_defense_mock.py -v`
When  it runs
Then  ≥ 14 tests pass and 0 fail

Given the source files for this story
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense_mock.py packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` runs
Then  exit code is 0

Given each modified or new file
When  wc -l is run
Then  each file is ≤ 400 LOC

Given §14 grep on the production hot path (excluding ai_defense_mock.py — §14 carve-out)
When  `grep -rE "(mock|fake|dummy|simulated)" packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py` runs
Then  the only matches are the env-var name "SPLUNKGATE_AI_DEFENSE_MOCK" and its docstring references
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Fixture matrix shape is correct
uv run python -c "
import json
from splunkgate_judges.ai_defense_types import InspectResponse, AIDefenseRule, Severity
m = json.load(open('packages/splunkgate_judges/src/splunkgate_judges/_fixtures/ai_defense_matrix.json'))
assert len(m) == 44, f'expected 44, got {len(m)}'
rules = set()
sevs = set()
for entry in m:
    resp = InspectResponse.model_validate(entry)
    sevs.add(resp.severity.value if hasattr(resp.severity, 'value') else resp.severity)
    for r in resp.rules:
        rules.add(r.rule_name.value if hasattr(r.rule_name, 'value') else r.rule_name)
assert sevs == {'NONE_SEVERITY','LOW','MEDIUM','HIGH'}, sevs
assert rules == {r.value for r in AIDefenseRule}, rules ^ {r.value for r in AIDefenseRule}
print('OK')
"
# Must print 'OK'

# Env-var toggle works
SPLUNKGATE_AI_DEFENSE_MOCK=1 uv run python -c "
from splunkgate_judges.ai_defense import AIDefenseClient
c = AIDefenseClient.from_env()
assert type(c).__name__ == 'MockAIDefenseClient'
print('OK')
"
# Must print 'OK'

# Without env vars, factory refuses
uv run python -c "
import os
os.environ.pop('SPLUNKGATE_AI_DEFENSE_MOCK', None)
os.environ.pop('SPLUNKGATE_AI_DEFENSE_API_KEY', None)
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges._errors import AIDefenseAuthError
try:
    AIDefenseClient.from_env()
    raise SystemExit('expected AIDefenseAuthError')
except AIDefenseAuthError as e:
    assert 'SPLUNKGATE_AI_DEFENSE_API_KEY' in str(e)
print('OK')
"
# Must print 'OK'

# Tests pass
uv run pytest packages/splunkgate_judges/tests/test_ai_defense_mock.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 14

# Strict typecheck
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/ai_defense_mock.py packages/splunkgate_judges/src/splunkgate_judges/ai_defense.py
# Must exit 0

# 400-LOC cap
for f in packages/splunkgate_judges/src/splunkgate_judges/ai_defense_mock.py packages/splunkgate_judges/src/splunkgate_judges/_fixtures/__init__.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7**, the 11 canonical rule names are verbatim: Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats. The fixture matrix must enumerate exactly these 11 names — no DefenseClaw additions.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §6, Cisco AI Defense Inspection API response field is `rules`, NOT `triggered_rules`.** Every fixture must use the key `rules`.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §6, severity enum includes NONE_SEVERITY.** Every fixture's `severity` field uses one of the verbatim strings: `NONE_SEVERITY`, `LOW`, `MEDIUM`, `HIGH`.
- The `ai_defense_mock.py` filename is a §14 carve-out per `architecture.md` § "Submission checklist gates" — mock data in this file is explicitly permitted because the file name signals intent. The §14 grep rule excludes `*_mock.py`.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — the mock dispatcher logs `aidefense.mock.hit` events to support eval-runtime tracking; the same counter shape ports to live mode without code change.
- Deterministic dispatch: `hash(trigger_text) % len(matrix)` is **not** deterministic across Python invocations (`PYTHONHASHSEED`). Use a stable mapping (e.g., `hashlib.sha256(text.encode()).hexdigest()[:8]` as integer key into a sorted matrix) or, preferably, an explicit `trigger_string → fixture_index` table embedded in the JSON.
- Fixture trigger strings should look realistic (e.g., for PII: `"my ssn is 123-45-6789"`; for Prompt Injection: `"ignore previous instructions and..."`; for PCI: `"4242 4242 4242 4242"`) so eval recordings demonstrate the matrix end-to-end visually.
- `from_env()` log shape: emit a single structlog INFO event `aidefense.client.constructed` with `mode="mock"|"live"`, `region`, no API key value.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the demo-recording path — `SPLUNKGATE_AI_DEFENSE_MOCK=1` runs the demo deterministically; flipping it off + setting `SPLUNKGATE_AI_DEFENSE_API_KEY` from the Explorer Edition UI replays the same demo against the live tenant for the "look it's real" segment of the screencast.

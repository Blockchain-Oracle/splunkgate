# Story — AI Defense end-to-end integration test (FastAPI fake + live gate)

**ID:** story-judges-05-ai-defense-end-to-end-integration-test
**Epic:** EPIC-04 — Cisco AI Defense Inspection API client
**Depends on:** story-judges-03-ai-defense-circuit-breaker-tenacity, story-judges-04-ai-defense-mock-respx-fixtures
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** SplunkGate maintainer about to ship to a hackathon submission deadline
**I want to** prove the AI Defense client survives retries, circuit-breaker trips, and produces a correct `splunkgate_core.Verdict` against both an in-process FastAPI fake and (optionally, when an API key is set) the real Explorer Edition tenant
**So that** the live integration is verified end-to-end, not just unit-tested in isolation, and the demo path is guaranteed to work without surprises

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_judges/tests/integration/__init__.py` — NEW — empty
- `packages/splunkgate_judges/tests/integration/fake_ai_defense_server.py` — NEW — a FastAPI app exposing `POST /api/v1/inspect/chat`; reads a deterministic policy table; returns `InspectResponse`-shaped JSON; supports an injectable `failure_mode` (`"503-twice"`, `"401"`, `"timeout"`, `"happy"`) controlled via a header `X-Fake-AIDefense-Policy`
- `packages/splunkgate_judges/tests/integration/test_ai_defense_end_to_end.py` — NEW — ≥ 10 tests: client→fake happy path returns parsed `InspectResponse`; client→fake retries exhausted converts to circuit-breaker tick; 3 consecutive failures trip the breaker; recovery probe succeeds; `to_verdict()` mapping converts an `InspectResponse` to a valid `splunkgate_core.Verdict` with matching severity, rules, classifications, explanation; the verdict's `surface` field is set to `"judges_ai_defense"` (or per the surface enum); response includes `attack_technique` and `event_id` when present
- `packages/splunkgate_judges/src/splunkgate_judges/_verdict_mapping.py` — NEW — `inspect_response_to_verdict(resp: InspectResponse, *, trace_id, surface, latency_ms) -> Verdict` — the canonical mapping
- `packages/splunkgate_judges/tests/integration/test_ai_defense_live.py` — NEW — gated on `SPLUNKGATE_AI_DEFENSE_API_KEY`; skipped via `pytest.skip` when unset; when set, runs a single deterministic prompt against the configured region (env `SPLUNKGATE_AI_DEFENSE_REGION`, default `"us"`) and asserts `is_safe`/`severity` shape is one of the documented enums

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the FastAPI fake is started in-process on a free port
When  AIDefenseClient is pointed at http://127.0.0.1:<port> and inspect_chat is called with a "PII" trigger
Then  the parsed InspectResponse has severity in {"LOW","MEDIUM","HIGH"} and at least one rules entry with rule_name=="PII"
And   the parsed response's rules field exists and triggered_rules does NOT exist as an attribute

Given the FastAPI fake is configured with policy "503-twice"
When  inspect_chat is called once
Then  the request retries twice and succeeds on the 3rd
And   the circuit-breaker state remains CLOSED (single user-visible failure-then-success)

Given the FastAPI fake is configured to always 503
When  inspect_chat is called 3 times sequentially
Then  the circuit-breaker transitions CLOSED → OPEN
And   the 4th call raises AIDefenseCircuitOpenError before reaching the wire

Given an InspectResponse with severity="HIGH", classifications=["PRIVACY_VIOLATION"], rules=[{rule_name:"PII",classification:"PRIVACY_VIOLATION",entity_types:["SSN"]}], explanation="contains an SSN"
When  inspect_response_to_verdict(resp, trace_id=UUID, surface="judges_ai_defense", latency_ms=42.0) is called
Then  the returned Verdict has severity=="HIGH", verdict in {"BLOCK","REVIEW"}, rules length >= 1, rules[0].rule == "PII"
And   the Verdict's explanation field equals "contains an SSN"
And   Verdict.model_validate(verdict.model_dump()) round-trips without error

Given SPLUNKGATE_AI_DEFENSE_API_KEY is unset
When  `uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_live.py -v` runs
Then  every test is skipped with reason "SPLUNKGATE_AI_DEFENSE_API_KEY unset"
And   the exit code is 0

Given SPLUNKGATE_AI_DEFENSE_API_KEY is set to a real key
When  `uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_live.py -v` runs
Then  the test runs against the real endpoint and asserts shape compliance

Given the integration test file
When  `uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_end_to_end.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the new src files
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/_verdict_mapping.py` runs
Then  exit code is 0

Given each modified or new file
When  wc -l is run
Then  each file is ≤ 400 LOC
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# In-process integration suite passes
uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_end_to_end.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# Live suite gates correctly (no key → skipped, exit 0)
env -u SPLUNKGATE_AI_DEFENSE_API_KEY uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_live.py -v 2>&1 | grep -E "(SKIPPED|skipped)"
# Must print at least one SKIPPED line; exit code must be 0
env -u SPLUNKGATE_AI_DEFENSE_API_KEY uv run pytest packages/splunkgate_judges/tests/integration/test_ai_defense_live.py
# Must exit 0

# Verdict mapping round-trip
uv run python -c "
from uuid import uuid4
from splunkgate_judges.ai_defense_types import InspectResponse
from splunkgate_judges._verdict_mapping import inspect_response_to_verdict
from splunkgate_core.verdict import Verdict

resp = InspectResponse.model_validate({
    'is_safe': False,
    'severity': 'HIGH',
    'classifications': ['PRIVACY_VIOLATION'],
    'rules': [{'rule_name': 'PII', 'classification': 'PRIVACY_VIOLATION', 'entity_types': ['SSN']}],
    'attack_technique': 'data_exfiltration',
    'explanation': 'contains an SSN',
    'event_id': 'evt_x',
    'client_transaction_id': 'tx_y',
})
v = inspect_response_to_verdict(resp, trace_id=uuid4(), surface='judges_ai_defense', latency_ms=42.0)
Verdict.model_validate(v.model_dump())
print('OK')
"
# Must print 'OK'

# Strict typecheck
uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/_verdict_mapping.py
# Must exit 0

# 400-LOC cap
for f in packages/splunkgate_judges/src/splunkgate_judges/_verdict_mapping.py packages/splunkgate_judges/tests/integration/fake_ai_defense_server.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
# Must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §6, Cisco AI Defense Inspection API response field is `rules`, NOT `triggered_rules`.** The FastAPI fake must serve responses with the `rules` field. Do not name it `triggered_rules` "just to test the parser" — the parser already enforces the public-docs name and the fake should mirror real Cisco shape.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §6, severity enum includes NONE_SEVERITY.** Include at least one fake fixture row with `severity="NONE_SEVERITY"` to exercise the safe path of the mapping.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, the 10M queries/AI-app/year quota is verified** — the live-gated test runs exactly ONE request per CI invocation against Explorer Edition to keep the quota burn negligible. Do not loop the live test.
- FastAPI is a permitted test dependency (not banned). The architecture.md ban list only forbids FastAPI in the MCP server runtime context — using it in `tests/integration/` is fine.
- The fake runs in-process via `uvicorn.Config` + `uvicorn.Server` started on an ephemeral port; tear down in a pytest fixture.
- The `inspect_response_to_verdict` mapping is the boundary between the AI Defense schema and the SplunkGate `Verdict` schema. Severity → severity is a 1:1 mapping (both enums share string values). `is_safe=True` → `VerdictLabel.ALLOW`. `is_safe=False && severity in {LOW,MEDIUM}` → `VerdictLabel.REVIEW`. `is_safe=False && severity==HIGH` → `VerdictLabel.BLOCK`. The mapping rule is documented in `architecture.md` § "API schemas" and `docs/PRD.md` — re-cite there if the rule shifts.
- **Per `../../../context/07-cisco-stack/03-foundation-sec-models.md`, Foundation-Sec is positioned by Cisco as security copilot/generator, NOT as classifier. Used as EXPLAINER only.** The `Verdict.explanation` field in this story is populated from the `InspectResponse.explanation` (Cisco's own explanation). The Foundation-Sec re-explanation comes later in EPIC-05 and EPIC-06 — do NOT call Foundation-Sec from this story.
- Live test gating: use `pytest.mark.skipif(not os.environ.get("SPLUNKGATE_AI_DEFENSE_API_KEY"), reason="SPLUNKGATE_AI_DEFENSE_API_KEY unset")` on each test function, not on the module — that way `pytest -v` still lists the gated tests.
- Cisco AI Defense Explorer Edition (`https://explorer.aidefense.cisco.com/`, March 23 2026 launch, free US-corp-email signup) is the demo-recording path — generate the live API key from Explorer Edition's UI and pass via `SPLUNKGATE_AI_DEFENSE_API_KEY` to run the live test segment of the screencast. The Explorer key is rate-limited but should comfortably accommodate one demo run.

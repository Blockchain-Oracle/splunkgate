# Story — OpenTelemetry → Splunk HEC exporter for splunkgate_core

**ID:** story-core-05-otel-hec-exporter-config
**Epic:** EPIC-03 — Core domain types
**Depends on:** story-core-02-otel-evaluation-event-emitter
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** coding agent finishing a Surface 1 / Surface 2 / Surface 3 integration test that emits an OTel `gen_ai.evaluation.result` event from a real `Verdict`
**I want to** import a single `configure_hec_exporter(hec_url, hec_token, *, index="main", sourcetype="cisco_ai_defense:splunkgate_verdict")` from `splunkgate_core.otel_hec_exporter`, call it once at startup, and have every subsequent `emit_verdict_event(...)` call ship to Splunk HEC as a JSON event under the `cisco_ai_defense:splunkgate_verdict` sourcetype
**So that** the architecture promise that "every surface lands every verdict as an OTel event in Splunk" is actually executable end-to-end — without this bridge, OTel events emit and disappear, and the demo's dashboard counters never tick

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` — NEW — ~320 LOC. Implements a Splunk-HEC-shaped OTel exporter subclassing `opentelemetry.sdk.trace.export.SpanExporter` (or the OTel `LogExporter` if the GenAI events land as log records on the configured collector — pick exporter type to match where `emit_verdict_event` from story-core-02 emits the event). For each captured span/log event whose `name == "gen_ai.evaluation.result"`, builds the Splunk HEC envelope: `{"time": <epoch from event.timestamp>, "sourcetype": <configured sourcetype>, "source": "splunkgate-otel", "index": <configured index>, "host": socket.gethostname(), "event": {<all event.attributes flattened>}}`. POSTs batches to `${hec_url}/services/collector/event` with header `Authorization: Splunk ${hec_token}` via `httpx.AsyncClient` (per ADR-stack `httpx` not `requests`). Wraps in `tenacity` retry — exponential backoff on 5xx + `httpx.TransportError`, max 3 attempts, give-up logs WARN via structlog. Public surface: `class SplunkHECExporter(SpanExporter)`, `def configure_hec_exporter(hec_url: str, hec_token: str, *, index: str = "main", sourcetype: str = "cisco_ai_defense:splunkgate_verdict", batch_size: int = 50, flush_interval_s: float = 5.0) -> None` (installs a `BatchSpanProcessor`-wrapped exporter on the global tracer provider), `def shutdown_hec_exporter() -> None` (graceful flush + close). Reads env-var fallbacks: `SPLUNKGATE_SPLUNK_HEC_URL` / `SPLUNKGATE_SPLUNK_HEC_TOKEN` / `SPLUNKGATE_SPLUNK_INDEX` / `SPLUNKGATE_SPLUNK_HEC_SOURCETYPE`. mypy --strict clean. ≤ 400 LOC.
- `packages/splunkgate_core/src/splunkgate_core/__init__.py` — UPDATE — re-export `SplunkHECExporter`, `configure_hec_exporter`, `shutdown_hec_exporter`; update `__all__`.
- `packages/splunkgate_core/pyproject.toml` — UPDATE — add `httpx`, `tenacity` (already in workspace; declare here for clarity).
- `packages/splunkgate_core/tests/test_otel_hec_exporter.py` — NEW — ≥ 14 behavioral tests using `respx` to mock HEC endpoints: exporter starts and ships a single event (Splunk envelope shape verified); the four required envelope keys (`time`, `sourcetype`, `source`, `event`) appear in every POST body; default `sourcetype` is `"cisco_ai_defense:splunkgate_verdict"`; `Authorization: Splunk <token>` header set verbatim; `--index` flows through to the envelope; batch flush triggers at `batch_size` events; batch flush triggers at `flush_interval_s` timeout; 5xx retry path retries up to 3 times then logs WARN; 4xx is non-retryable and logs ERROR; env-var fallback for missing kwargs; `shutdown_hec_exporter` drains pending events before returning; concurrent `emit_verdict_event` from multiple coroutines all land; only `gen_ai.evaluation.result` events ship (other span events are dropped at the exporter); no real network call escapes (respx asserts).
- `packages/splunkgate_core/tests/conftest.py` — UPDATE (or NEW if not present from core-02) — adds `respx_mock` fixture configured to intercept `*/services/collector/event`; provides a `splunk_hec_envelope` Pydantic helper for assertion shorthand.

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`. In particular: **do not** modify `splunkgate_core/otel.py` from story-core-02 (this story consumes the events it emits, doesn't reshape them); **do not** add `requests` (banned per architecture); **do not** write the exporter as a generic OTel Splunk shim (it's SplunkGate-specific — name-filtered to `gen_ai.evaluation.result`).

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py exists
When  `uv run python -c "from splunkgate_core import configure_hec_exporter, shutdown_hec_exporter, SplunkHECExporter; print('ok')"` runs
Then  exit code is 0
And   stdout contains "ok"

Given respx mocks the HEC endpoint and configure_hec_exporter is called
When  one `emit_verdict_event(verdict)` is called and `shutdown_hec_exporter()` runs
Then  exactly one POST is made to `*/services/collector/event`
And   the POST body JSON has keys `time`, `sourcetype`, `source`, `event`

Given a POST is captured
When  the `sourcetype` field is inspected
Then  the default value is exactly "cisco_ai_defense:splunkgate_verdict"

Given a POST is captured
When  the `Authorization` header is inspected
Then  the value matches the regex `^Splunk [A-Za-z0-9_-]+$`

Given configure_hec_exporter(index="splunkgate_demo", sourcetype="cisco_ai_defense:splunkgate_verdict")
When  a verdict is emitted and the POST is captured
Then  the POST body has `index == "splunkgate_demo"`
And   `sourcetype == "cisco_ai_defense:splunkgate_verdict"`

Given batch_size=10 and 25 verdicts are emitted in quick succession
When  the test captures all POSTs after flush
Then  the number of HEC POSTs is ≥ 3 (batch flushes plus tail flush)
And   the total number of events shipped equals 25

Given the HEC endpoint returns HTTP 503 twice then 200
When  one verdict is emitted and the exporter retries
Then  the final outcome is 1 successful POST
And   the structlog output contains zero ERROR-level lines

Given the HEC endpoint returns HTTP 400
When  one verdict is emitted
Then  the exporter does NOT retry (non-retryable)
And   structlog output contains exactly one ERROR-level line citing 400

Given SPLUNKGATE_SPLUNK_HEC_URL and SPLUNKGATE_SPLUNK_HEC_TOKEN are set in the env and configure_hec_exporter() is called with no kwargs
When  a verdict is emitted
Then  the POST goes to the env-var URL with the env-var token

Given a span event whose name is "tool.invoked" (not gen_ai.evaluation.result) is emitted
When  the exporter processes it
Then  no HEC POST is made for that event

Given the test suite runs
When  `uv run pytest packages/splunkgate_core/tests/test_otel_hec_exporter.py -v` runs
Then  ≥ 14 tests pass and 0 fail

Given mypy strict mode is active
When  `uv run mypy --strict packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` runs
Then  exit code is 0

Given ruff is run
When  `uv run ruff check packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` runs
Then  exit code is 0

Given the 400-LOC rule
When  `wc -l packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on the changed source (excluding tests)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Imports resolve
uv run python -c "from splunkgate_core import configure_hec_exporter, shutdown_hec_exporter, SplunkHECExporter; print('ok')"

# 2. Tests pass (≥ 14)
uv run pytest packages/splunkgate_core/tests/test_otel_hec_exporter.py -v 2>&1 | tee /tmp/pytest.out
[ "$(grep -cE 'PASSED' /tmp/pytest.out)" -ge 14 ]

# 3. Strict typecheck
uv run mypy --strict packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py

# 4. Lint
uv run ruff check packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py

# 5. 400-LOC cap
[ "$(wc -l < packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py)" -le 400 ]

# 6. §14 clean (production code path)
! grep -E "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_core/src/splunkgate_core/otel_hec_exporter.py

# 7. Live HEC round-trip (gated on env vars per docs/architecture.md Hard Rule 6)
if [ -n "${SPLUNKGATE_SPLUNK_HEC_TOKEN:-}" ] && [ -n "${SPLUNKGATE_SPLUNK_HEC_URL:-}" ]; then
  uv run python - <<'PY'
import asyncio, uuid
from datetime import datetime, timezone
from splunkgate_core import configure_hec_exporter, shutdown_hec_exporter
from splunkgate_core.otel import emit_verdict_event
from splunkgate_core.verdict import Verdict, VerdictLabel, Severity

async def main():
    configure_hec_exporter()  # picks up env vars
    v = Verdict(
        trace_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        verdict=VerdictLabel.BLOCK,
        severity=Severity.HIGH,
        rules=[],
        explanation="round-trip smoke",
        surface="mw_model",
        latency_ms=42.0,
    )
    emit_verdict_event(v)
    shutdown_hec_exporter()
asyncio.run(main())
print("HEC round-trip ok")
PY
fi
echo "ALL CHECKS PASS"
```

All seven blocks must exit 0 before opening the PR (block 7 is conditional on env vars; otherwise skipped).

---

## Notes for coding agent

- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`**, the `gen_ai.evaluation.result` event is the spec slot SplunkGate emits. This exporter filters on `event.name == "gen_ai.evaluation.result"` and skips everything else — SplunkGate is not a general-purpose OTel-to-Splunk shim. If a future use case needs the generic shim, that's a separate package (and likely an upstream OTel exporter — do not invent here).
- **Per ADR-005 in `docs/architecture.md`**, the default sourcetype is `cisco_ai_defense:splunkgate_verdict` — load-bearing for colocation with Cisco Security Cloud (app 7404, 55K installs). Do not change the default.
- **Per `docs/architecture.md` § "Stack (locked)"**, use `httpx.AsyncClient` not `requests`, use `tenacity` for retry not hand-rolled backoff. Per Hard Rule 7, the exporter MUST default `verify=True` on TLS; if a dev needs self-signed certs they set `SPLUNKGATE_DEV_INSECURE_TLS=1` and the exporter logs a WARN at startup (do NOT silently `verify=False`).
- **Per `docs/architecture.md` Hard Rule 6 ("No real Splunk credentials in code or fixtures")**: tests use `respx` to mock the HEC endpoint. The live round-trip is gated on `SPLUNKGATE_SPLUNK_HEC_TOKEN`. Do not commit any token. Use `respx.MockRouter` to assert the exact Authorization header shape without ever issuing a real request.
- **Per the OTel SDK convention**, the right way to install an exporter is `trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(SplunkHECExporter(...)))`. The `BatchSpanProcessor` already handles batching + flush-on-shutdown — wrap it, don't reimplement the queue. The `batch_size` + `flush_interval_s` kwargs map to `BatchSpanProcessor`'s `max_export_batch_size` + `schedule_delay_millis`.
- **Per `docs/architecture.md` § "OTel emission shape"**, the Splunk HEC envelope must place the OTel event attributes inside the `event` field (NOT at the top level). Splunk's `props.conf` from `story-app-02` runs `INDEXED_EXTRACTIONS = json` on the `event` payload — so the dashboards see the flattened attributes as searchable fields.
- **Per `docs/architecture.md` § "Banned patterns"**, no `print()` for logs — use `structlog` (configured in story-core-04 `splunkgate_core.log`). Retry give-up and 4xx errors log via `structlog`.
- **Env-var fallback precedence** is kwarg > env var > raise. The error message must name which env vars to set. Do not silently default to a fake URL.
- **Concurrency**: the exporter must be safe to call from multiple coroutines. The `BatchSpanProcessor` is thread-safe; you only need to ensure the `httpx.AsyncClient` is reused (one per exporter instance) and closed on shutdown.
- **Tenacity retry config**: `retry=retry_if_exception_type((httpx.TransportError,)) | retry_if_result(lambda r: 500 <= r.status_code < 600)`, `stop=stop_after_attempt(3)`, `wait=wait_exponential(multiplier=1, max=10)`. Do not retry 4xx — those are caller errors (bad token, bad index).
- **The `shutdown_hec_exporter()` function must drain pending events before returning**; tests assert this by emitting N events without explicit flush and asserting all N land after shutdown.
- **Surface 4 (Splunk app) consumes these events** — the `event` payload's keys MUST match what `story-app-02`'s `FIELDALIAS-*` lines expect: `gen_ai.evaluation.score.label`, `gen_ai.evaluation.score.value`, `gen_ai.evaluation.explanation`, `splunkgate.surface`, `splunkgate.rules` (array of strings), `splunkgate.trace_id`, optionally `mcp.method.name` + `mcp.session.id`. Verify the post-flush envelope shape against `story-app-02`'s acceptance criteria.
- **mypy --strict requires explicit types on all `kwargs` and return values**. `dict[str, Any]` is the only place `Any` is allowed (HEC event payload is intentionally schema-flexible — but SplunkGate emits Verdict-shaped events only). Cite this carve-out inline.
- **Story `story-eval-06` consumes this** — the end-to-end integration test calls `configure_hec_exporter` with live credentials and asserts the SPL query returns the emitted event. Wire the exporter so that demo path works.
- Estimate breakdown: ~30 min OTel SpanExporter scaffold + httpx async client, ~30 min HEC envelope shape + sourcetype filter, ~30 min tenacity retry + structlog wiring, ~45 min test suite (14 cases via respx), ~15 min env-var fallback + shutdown semantics.

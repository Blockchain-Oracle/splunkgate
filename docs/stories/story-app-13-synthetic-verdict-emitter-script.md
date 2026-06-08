# Story — Synthetic verdict emitter script: Synthetic-Data/scripts/emit_sample_verdict.py

**ID:** story-app-13-synthetic-verdict-emitter-script
**Epic:** EPIC-09 — Surface 4 Splunk app
**Depends on:** story-app-02-props-transforms-for-splunkgate-verdict-sourcetype, story-eval-01-synthetic-data-generator-dns-guard-pattern
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** demo operator (or `story-app-10` vision-loop, or `story-demo-01` screencast author) preparing the Splunk dashboards for judges
**I want to** run a single `python Synthetic-Data/scripts/emit_sample_verdict.py --count 500 --hec-url ${SPLUNKGATE_SPLUNK_HEC_URL} --hec-token ${SPLUNKGATE_SPLUNK_HEC_TOKEN}` command and have ≥ 500 realistic SplunkGate `Verdict` events appear in Splunk under `sourcetype="cisco_ai_defense:splunkgate_verdict"` within 30 seconds
**So that** the three Dashboard Studio v2 dashboards (Agent Risk Overview / Verdict Inspector / Regulator Evidence Pack) render with non-empty data for demo beat 1 ("Open dashboard, see live counters") and the vision-loop in story-app-10 has events to screenshot against

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `Synthetic-Data/scripts/emit_sample_verdict.py` — NEW — ~250 LOC Python 3.13 stdlib + `httpx` script. Reads ≥ 1 record from each of `Synthetic-Data/jailbreak_corpus/tool_call_abuse.jsonl`, `Synthetic-Data/jailbreak_corpus/multi_turn_injection.jsonl`, `Synthetic-Data/jailbreak_corpus/benign_control.jsonl`, and `Synthetic-Data/pii_leak_corpus/imprompter_payloads.jsonl` (the last produced by `story-eval-03`). For each input record, synthesizes a fully populated `Verdict` (every field per `splunkgate_core.verdict.Verdict` per `docs/architecture.md` § "Verdict") with realistic distributions: ~70 % `ALLOW`, ~15 % `BLOCK`, ~10 % `MODIFY`, ~5 % `REVIEW`; severity weighted to label; `surface` cycled across the 8 enumerated values (`mw_model`, `mw_tool`, `mw_subagent`, `mcp_score`, `mcp_judge_tool`, `mcp_check_output`, `mcp_audit`, `defenseclaw`); `rules` drawn from the 11 verbatim Cisco AI Defense rule names per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7; `latency_ms` log-normal around 120 ms; `timestamp` jittered across the last 24 h so dashboards show a time-series. Wraps each Verdict in the OTel `gen_ai.evaluation.result` event shape per `docs/architecture.md` § "OTel emission shape" (top-level `event` key with `gen_ai.evaluation.*` + `splunkgate.*` + optional `mcp.*` attributes), POSTs batched to `${HEC_URL}/services/collector/event` with `Authorization: Splunk ${HEC_TOKEN}` header, `sourcetype: cisco_ai_defense:splunkgate_verdict`, `source: splunkgate-synthetic`. CLI flags: `--count INT` (default 500), `--hec-url`, `--hec-token`, `--index` (default `main`), `--seed INT` (default 20260603 — deterministic), `--dry-run` (writes events to stdout as JSON, skips HTTP). Exit codes: 0 success, 1 invalid arg, 2 HEC POST failed > 3 retries, 3 input corpora missing.
- `Synthetic-Data/scripts/__init__.py` — NEW — empty package marker (so the directory is importable for tests).
- `Synthetic-Data/scripts/README.md` — NEW — short doc: purpose, CLI usage, env-var precedence (`SPLUNKGATE_SPLUNK_HEC_URL` / `SPLUNKGATE_SPLUNK_HEC_TOKEN` override flags), §14 carve-out disclaimer (synthetic events are demo-only fixtures, not production telemetry), citation to `docs/architecture.md` ADR-005.
- `Synthetic-Data/scripts/tests/__init__.py` — NEW — empty marker.
- `Synthetic-Data/scripts/tests/test_emit_sample_verdict.py` — NEW — ≥ 10 behavioral tests using `--dry-run` mode + `respx` for the HEC POST: dry-run produces ≥ N events for `--count N`; every emitted event validates against `splunkgate_core.verdict.Verdict.model_validate(event["event"])`; `sourcetype` field equals `"cisco_ai_defense:splunkgate_verdict"` in every POST body; verdict-label distribution matches the configured weights ±5 % over `--count 1000`; the 4 input corpora are required (exit code 3 if any missing); `--seed` produces deterministic byte-identical output across two runs; `surface` field cycles through all 8 enum values for `--count ≥ 8`; `rules[]` only contains values from the verbatim 11-rule list; `--hec-url`/`--hec-token` precedence (flag > env > raise); HEC retry path covers 503 → 503 → 200 success via respx.

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`. In particular: **do not** modify `splunk_apps/splunkgate_app/` from this story, **do not** add `numpy` / `pandas` / `faker` (stdlib + `httpx` only per `docs/architecture.md` § "Banned"), **do not** write to a real Splunk endpoint without the env vars present (the test suite uses respx + `--dry-run`).

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the script exists
When  `uv run python Synthetic-Data/scripts/emit_sample_verdict.py --help` runs
Then  exit code is 0
And   stdout contains "--count", "--hec-url", "--hec-token", "--dry-run", "--seed"

Given the four input corpora exist (tool_call_abuse, multi_turn_injection, benign_control, imprompter_payloads)
When  `uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 500 --dry-run` runs
Then  exit code is 0
And   stdout contains ≥ 500 JSON lines

Given the dry-run output is captured
When  every emitted event's `event` field is parsed as JSON and validated against `splunkgate_core.verdict.Verdict`
Then  zero validation errors are raised

Given the dry-run output is captured
When  every event's `sourcetype` is inspected
Then  every value equals exactly "cisco_ai_defense:splunkgate_verdict"

Given the dry-run output for --count 1000 --seed 20260603
When  the distribution of verdict labels is computed
Then  ALLOW is within 65-75%, BLOCK is within 10-20%, MODIFY is within 5-15%, REVIEW is within 2-8%

Given any of the four input corpora is removed
When  `uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 10 --dry-run` runs
Then  exit code is 3

Given the same --count and --seed are used twice
When  outputs are compared via `sha256sum`
Then  the hashes match (deterministic)

Given --count 100 --dry-run
When  the set of `splunkgate.surface` attribute values across all events is collected
Then  the set is a subset of {mw_model, mw_tool, mw_subagent, mcp_score, mcp_judge_tool, mcp_check_output, mcp_audit, defenseclaw}
And   at least 6 distinct values appear

Given --count 100 --dry-run
When  the set of rule names across all events is collected
Then  every rule name is in the verbatim 11-rule list (Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity, Prompt Injection, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats)

Given an env with respx mocking a 503/503/200 HEC sequence
When  `uv run pytest Synthetic-Data/scripts/tests/test_emit_sample_verdict.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the script source file
When  `wc -l Synthetic-Data/scripts/emit_sample_verdict.py` runs
Then  the line count is ≤ 400

Given the §14 grep is run on the production code path (the script itself is a §14 carve-out — synthetic fixture generator)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" Synthetic-Data/scripts/emit_sample_verdict.py` runs
Then  output is allowed (script IS the synthetic fixture; carve-out documented in Synthetic-Data/scripts/README.md per docs/architecture.md § "submission checklist gates")
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Script + tests exist
test -f Synthetic-Data/scripts/emit_sample_verdict.py
test -f Synthetic-Data/scripts/README.md
test -f Synthetic-Data/scripts/tests/test_emit_sample_verdict.py

# 2. --help works
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --help > /tmp/help.txt
grep -q -- "--count"     /tmp/help.txt
grep -q -- "--hec-url"   /tmp/help.txt
grep -q -- "--hec-token" /tmp/help.txt
grep -q -- "--dry-run"   /tmp/help.txt
grep -q -- "--seed"      /tmp/help.txt

# 3. Dry-run produces ≥ 500 valid Verdict events
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 500 --dry-run > /tmp/events.jsonl
[ "$(wc -l < /tmp/events.jsonl)" -ge 500 ]

uv run python - <<'PY'
import json
from splunkgate_core.verdict import Verdict
bad = 0
sourcetypes = set()
surfaces = set()
labels = []
rules = set()
ALLOWED_RULES = {
    "Code Detection","Harassment","Hate Speech","PCI","PHI","PII",
    "Profanity","Prompt Injection","Sexual Content & Exploitation",
    "Social Division & Polarization","Violence & Public Safety Threats",
}
ALLOWED_SURFACES = {"mw_model","mw_tool","mw_subagent","mcp_score","mcp_judge_tool","mcp_check_output","mcp_audit","defenseclaw"}
for line in open("/tmp/events.jsonl"):
    rec = json.loads(line)
    sourcetypes.add(rec["sourcetype"])
    try:
        v = Verdict.model_validate(rec["event"])
    except Exception as e:
        bad += 1
        continue
    surfaces.add(v.surface)
    labels.append(v.verdict.value)
    for r in v.rules:
        rules.add(r.rule)
assert bad == 0, f"{bad} invalid Verdicts"
assert sourcetypes == {"cisco_ai_defense:splunkgate_verdict"}, sourcetypes
assert surfaces.issubset(ALLOWED_SURFACES), surfaces - ALLOWED_SURFACES
assert rules.issubset(ALLOWED_RULES), rules - ALLOWED_RULES
print("schema OK")
PY

# 4. Determinism — same --seed yields byte-identical output
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 100 --seed 20260603 --dry-run > /tmp/a.jsonl
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 100 --seed 20260603 --dry-run > /tmp/b.jsonl
[ "$(sha256sum < /tmp/a.jsonl)" = "$(sha256sum < /tmp/b.jsonl)" ]

# 5. Verdict-label distribution within tolerance
uv run python - <<'PY'
import json, collections
ctr = collections.Counter()
n = 0
for line in open("/tmp/events.jsonl"):
    rec = json.loads(line)
    ctr[rec["event"]["verdict"]] += 1
    n += 1
allow_pct = ctr.get("ALLOW", 0) * 100 / n
block_pct = ctr.get("BLOCK", 0) * 100 / n
modify_pct = ctr.get("MODIFY", 0) * 100 / n
review_pct = ctr.get("REVIEW", 0) * 100 / n
assert 65 <= allow_pct <= 75, f"ALLOW {allow_pct}"
assert 10 <= block_pct <= 20, f"BLOCK {block_pct}"
assert 5 <= modify_pct <= 15, f"MODIFY {modify_pct}"
assert 2 <= review_pct <= 8, f"REVIEW {review_pct}"
print(f"dist OK: A={allow_pct:.1f} B={block_pct:.1f} M={modify_pct:.1f} R={review_pct:.1f}")
PY

# 6. Missing-corpus path returns exit 3
mv Synthetic-Data/jailbreak_corpus/tool_call_abuse.jsonl /tmp/.backup.jsonl
set +e
uv run python Synthetic-Data/scripts/emit_sample_verdict.py --count 10 --dry-run >/dev/null 2>&1
rc=$?
set -e
mv /tmp/.backup.jsonl Synthetic-Data/jailbreak_corpus/tool_call_abuse.jsonl
[ "$rc" -eq 3 ]

# 7. Test suite ≥ 10 PASSED
uv run pytest Synthetic-Data/scripts/tests/test_emit_sample_verdict.py -v 2>&1 | tee /tmp/pytest.out
[ "$(grep -cE 'PASSED' /tmp/pytest.out)" -ge 10 ]

# 8. 400-LOC cap on the script
[ "$(wc -l < Synthetic-Data/scripts/emit_sample_verdict.py)" -le 400 ]

# 9. Live HEC round-trip (gated on env vars)
if [ -n "${SPLUNKGATE_SPLUNK_HEC_TOKEN:-}" ] && [ -n "${SPLUNKGATE_SPLUNK_HEC_URL:-}" ]; then
  uv run python Synthetic-Data/scripts/emit_sample_verdict.py \
    --count 50 \
    --hec-url  "${SPLUNKGATE_SPLUNK_HEC_URL}" \
    --hec-token "${SPLUNKGATE_SPLUNK_HEC_TOKEN}"
fi
echo "ALL CHECKS PASS"
```

All blocks must exit 0 before opening the PR (block 9 is conditional on env vars; otherwise skipped).

---

## Notes for coding agent

- **Per ADR-005 in `docs/architecture.md`**, sourcetype `cisco_ai_defense:splunkgate_verdict` is load-bearing — it colocates with Cisco Security Cloud (app 7404 v3.6.6, 55K installs) so SOC analysts get unified search. Do NOT change the sourcetype string. The `props.conf` stanza from `story-app-02` parses on this exact value.
- **Per `docs/architecture.md` § "OTel emission shape"**, each event posted to HEC is `{"time": <epoch>, "sourcetype": "cisco_ai_defense:splunkgate_verdict", "source": "splunkgate-synthetic", "index": "<index>", "event": {<top-level Verdict JSON> + dotted OTel attrs}}`. Splunk HEC strips the outer envelope and the props.conf `INDEXED_EXTRACTIONS = json` lifts the `event` payload into fields.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7, the 11 canonical AI Defense rules are verbatim:** `Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Prompt Injection, Profanity, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats`. Use these exact strings (ampersands, capitalization, spacing). The audit synthesis `2026-06-03-audit-synthesis.md` A-6 fixed the historical hallucination — do not regress.
- **Per `docs/architecture.md` § "Banned patterns"** and § "Stack (locked)": stdlib + `httpx` only. No `numpy`, no `pandas`, no `faker`. The DNS Guard 2025 `generate_dns_events.py` (`../inspiration/Splunk-DNS-Guard-AI/Syntethic-Data/generate_dns_events.py`) is the structural model — single file, deterministic seed, stdlib heavy.
- **Per `docs/architecture.md` Hard Rule 6 ("No real Splunk credentials in code or fixtures")**: tests use `--dry-run` + respx; the live HEC round-trip (shell block 9) only runs if `SPLUNKGATE_SPLUNK_HEC_TOKEN` is set. Do not bake any token into the script or tests.
- **§14 carve-out**: this script's purpose IS to synthesize fixture events for demos. Annotate the module docstring with `# §14 CARVE-OUT: synthetic fixture generator for demo + vision-loop. Not a production telemetry path.` and document the carve-out in `Synthetic-Data/scripts/README.md`. The §14 grep on production paths (`packages/splunkgate_*/src/`) does NOT cover `Synthetic-Data/`; see `docs/architecture.md` § "submission checklist gates".
- **HEC retry path** uses `tenacity` (already pinned via `splunkgate_judges` per EPIC-04) — retry on HTTP 5xx / connection errors with exponential backoff capped at 3 attempts; on final failure return exit 2.
- **Determinism is load-bearing for the vision loop in `story-app-10`** — the anchor screenshots are computed against a specific event distribution. Same `--seed` + `--count` MUST produce byte-identical stdout in `--dry-run`. Use `random.Random(seed)` (not the global RNG) so concurrent processes don't interfere.
- **The verdict label/severity distribution mirrors a realistic demo deployment** — heavy ALLOW (agents mostly do safe things), tail BLOCK/MODIFY (the interesting cases the demo highlights). Numbers cited in the BDD criteria match `docs/eval-spec.md` baseline expectations.
- **CLI surface**: prefer `argparse` (stdlib) over `click` / `typer` (extra deps). Print one JSON event per stdout line in `--dry-run` (the BDD assertions parse line-by-line).
- **Input corpora paths** are exact: `Synthetic-Data/jailbreak_corpus/{tool_call_abuse,multi_turn_injection,benign_control}.jsonl` (from `story-eval-01`) + `Synthetic-Data/pii_leak_corpus/imprompter_payloads.jsonl` (from `story-eval-03`). If `story-eval-03` hasn't landed, gate the imprompter pull with `pathlib.Path(...).exists()` and log a warning — but exit 3 if any of the three jailbreak corpora are missing (those are hard dependencies via `story-eval-01`).
- This story's depends_on (`story-app-02` + `story-eval-01`) reflects the consumer (sourcetype config from app-02) + producer (corpora from eval-01) relationship. The script is consumed by `story-app-10` (vision loop) and `story-demo-01` (screencast); both currently inline a `[ -f ... ]` guard waiting for this script.
- Estimate breakdown: ~30 min argparse + IO scaffolding, ~45 min verdict synthesis + OTel envelope, ~30 min HEC POST + retry, ~30 min tests + dry-run determinism check, ~15 min docs + README.

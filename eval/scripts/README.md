# SplunkGate eval scripts

CLI drivers for the eval harness.

## `run_full.py`

Full eval driver — iterates `BASELINES × DATASETS`, writes per-dataset
JSON under `eval/results/<git-sha>/`, then calls `generate_report` to
produce `summary.md` + a mirror to `docs/eval-results.md` (gitignored;
nightly main-branch CI is the canonical writer).

```bash
SPLUNKGATE_AI_DEFENSE_MOCK=1 SPLUNKGATE_GPT_OSS_MOCK=1 \
  uv run python eval/scripts/run_full.py --limit 50
```

## `smoke.py`

Smoke driver — 2 baselines × 2 datasets × `--limit 25` ≈ 100 verdicts.
Exits 0 in <60 s. Required by `cicd-06-eval-smoke-job`.

## `e2e_demo.py`

End-to-end demo dress-rehearsal. Runs the verbatim PRD demo prompt-
injection payload through the `splunkgate_mw.examples.support_agent`,
asserts SplunkGate blocks it with the expected Verdict shape, then
polls Splunk via SPL to verify the matching row landed via the
OTel → HEC pipeline.

```bash
export SPLUNKGATE_SPLUNK_HEC_URL=https://splunk.example.com:8088
export SPLUNKGATE_SPLUNK_HEC_TOKEN=eyJraWQ...
export SPLUNKGATE_SPLUNK_HOST=splunk.example.com
export SPLUNKGATE_SPLUNK_API_TOKEN=eyJraWQ...
uv run python eval/scripts/e2e_demo.py --timeout 60
```

### Exit codes

| Code | Meaning |
|---:|---|
| 0 | SUCCESS — demo prompt blocked + verdict landed in Splunk |
| 1 | SplunkGate did NOT block the malicious prompt (safety net broken) |
| 2 | Verdict emitted in-process but never reached Splunk within `--timeout` |
| 3 | In-process Verdict and SPL result row disagree (label/severity/rule) |
| 4 | Required env var missing — names the var in stderr |

### Flags

- `--prompt STRING` — default = verbatim PRD payload
- `--profile STRING` — default `financial_services`
- `--timeout INT` — SPL poll timeout seconds (default 30)
- `--earliest STRING` — SPL `earliest_time` window (default `-5m`)
- `--print-default-prompt` — dump the verbatim PRD payload and exit 0

### Consumer

`story-demo-01` (the screencast) calls this script as the dress-
rehearsal smoke test the day before recording. Exit 0 = the demo will
work on camera.

Live e2e is **gated on env vars** — the test suite covers the unit
behaviour without a Splunk dependency.

# Synthetic-Data — fixture generator

Single-purpose helper scripts for populating SplunkGate dashboards + the
story-app-10 vision-loop with demo data.

## §14 carve-out

This directory is a documented §14 ("no mocks in production") carve-out per
`docs/architecture.md` § "submission checklist gates". Scripts here generate
**synthetic fixture events** for demos + screencast + anchor capture; they
are not on any production telemetry path. The production path is
`splunkgate_mw → splunkgate_core/otel.py → splunklib HEC export`.

The §14 grep (`scripts/check_loc.py` + `.github/workflows/ci.yml`) is scoped
to `packages/splunkgate_*/src/` and intentionally excludes this directory.

## `emit_sample_verdict.py`

Produces N realistic `Verdict` events shaped as Splunk HEC payloads under
sourcetype `cisco_ai_defense:splunkgate_verdict`. Verdicts:

- Distribution: ~70 % ALLOW, ~15 % BLOCK, ~10 % MODIFY, ~5 % REVIEW.
- Severity correlates with label (ALLOW skews NONE_SEVERITY/LOW, BLOCK skews HIGH).
- Surface cycles across all 8 enumerated values (mw_*, mcp_*, defenseclaw).
- Rules drawn from the verbatim 11-rule Cisco AI Defense list per
  `../../context/07-cisco-stack/01-ai-defense-deep.md`.
- Latency log-normal around 120 ms.
- Timestamps jittered across the last 24 h so dashboards show a time series.
- Deterministic by `--seed` (default 20260603).

### CLI

```bash
# Dry run — print events to stdout, one JSON envelope per line.
python Synthetic-Data/scripts/emit_sample_verdict.py --count 500 --dry-run

# Live emit to Splunk HEC.
python Synthetic-Data/scripts/emit_sample_verdict.py \
    --count 500 \
    --hec-url $SPLUNKGATE_SPLUNK_HEC_URL \
    --hec-token $SPLUNKGATE_SPLUNK_HEC_TOKEN
```

### Env-var precedence

`--hec-url` flag overrides `SPLUNKGATE_SPLUNK_HEC_URL` env var; `--hec-token`
flag overrides `SPLUNKGATE_SPLUNK_HEC_TOKEN`. Live mode requires both. Per
Hard Rule 6, no real credentials are baked into the script or tests.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success — events emitted (or printed in `--dry-run`) |
| 1 | Invalid CLI argument OR live mode requested without HEC creds |
| 2 | HEC POST failed after 3 retries |

### Determinism

Vision-loop anchor screenshots (story-app-10) depend on this script
producing byte-identical stdout for the same `--seed` + `--count`. Uses
`random.Random(seed)` (not the global RNG) so concurrent processes don't
interfere.

## Cross-references

- `docs/architecture.md` ADR-005 — sourcetype `cisco_ai_defense:splunkgate_verdict` colocates with Cisco Security Cloud (Splunkbase 7404).
- `docs/architecture.md` § "OTel emission shape" — HEC envelope format.
- `docs/stories/story-app-13-synthetic-verdict-emitter-script.md` — story spec.
- `docs/stories/story-app-10-app-vision-loop-validation.md` — consumes the deterministic stdout.

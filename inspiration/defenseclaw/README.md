# Vendored DefenseClaw artefacts

This directory contains a minimal vendored slice of
[cisco-ai-defense/defenseclaw](https://github.com/cisco-ai-defense/defenseclaw)
required by `story-eval-04` — namely:

- `internal/gateway/rules.go` — the canonical Pattern-Rule declarations
  (115 `regexp.MustCompile(...)` constants) that
  `eval/src/splunkgate_eval/baselines/_regex_loader.py` parses to drive
  the `defenseclaw_regex_only` eval baseline.
- `LICENSE` — Apache-2.0 © Cisco Systems, Inc. 2026, verbatim.

> **SplunkGate does not fork DefenseClaw.** Per `integrations/defenseclaw/README.md`,
> Surface 3 is a config delta only. This vendored slice exists *for the
> eval harness only* — the regex baseline reads the patterns at parse
> time so the eval can compare DefenseClaw-regex-alone against the
> SplunkGate full stack. No DefenseClaw Go code is rebuilt or shipped
> as part of any SplunkGate runtime.

When the upstream DefenseClaw repo can be cloned reliably (the
2026-06-11 clone attempt failed with `fetch-pack: invalid index-pack
output` on the hackathon network), the recommended layout is to
replace this directory with a git submodule pinned to a stable commit.
For now `rules.go` is curl-fetched from the upstream main branch as
of 2026-06-11.

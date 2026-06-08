# Pre-commit installation

Pre-commit hooks live in `../../.pre-commit-config.yaml` (repo root). They gate `git commit` locally so violations are caught on your laptop in <10s instead of after a 5-minute CI round-trip.

## Install once

```bash
uv sync --all-packages --frozen
uv run pre-commit install
```

This writes `.git/hooks/pre-commit` to your local clone. Every subsequent `git commit` runs the hook chain against staged files.

## Hooks active

| Hook | Catches |
|---|---|
| `ruff` (`--fix`) | Lint violations + auto-fix |
| `ruff-format` | Formatter drift |
| `mypy --strict` (on `splunkgate_core`/`splunkgate_judges` only) | Type errors in the load-bearing packages |
| `check-loc-400` | Any `*.py` file exceeding 400 LOC |
| `no-print` | `print(` in production code (use `structlog` instead) |
| `gitleaks` | Committed secrets (AWS keys, tokens, etc.) |

## Bypass policy

**Default:** Do not pass `--no-verify` to `git commit`.

**Emergency only:** if you must bypass (e.g., committing a stub during a partial outage of a hook tool), document the reason in your PR description and follow up with a fix-forward commit that re-introduces the hook gate. PR review will reject any change that suppresses a hook without justification.

For the LOC cap there is **no** `# noqa: loc-cap` escape hatch. Split via composition or extraction.

If gitleaks flags a file, the secret must be **rotated** AND history rewritten with `git-filter-repo` — do not add the file to the gitleaks allowlist.

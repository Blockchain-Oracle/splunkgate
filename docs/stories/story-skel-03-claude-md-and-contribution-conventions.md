# Story — CLAUDE.md + CONTRIBUTING.md + PR template

**ID:** story-skel-03-claude-md-and-contribution-conventions
**Epic:** EPIC-02 — Repo skeleton + coding standards
**Depends on:** story-skel-01-uv-workspace-pyproject
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent (or human reviewer) opening or reviewing a PR
**I want to** have a single `CLAUDE.md` at the repo root that codifies the coding standards from `docs/architecture.md`, plus a `CONTRIBUTING.md` and a `.github/PULL_REQUEST_TEMPLATE.md` that force every PR description to cite back into `context/`
**So that** no PR is ambiguous about "what's the rule here" and every load-bearing claim in a PR can be traced to primary-source-grounded evidence in `context/`

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `CLAUDE.md` — NEW — repo-root agent contract: stack pin, ≤400-LOC rule, mypy-strict scope, ruff config, banned patterns (`requests`, `verify=False`, `Any` in core/judges, `unittest.mock` for HTTP), context/-citation rule, file-modification-map discipline
- `CONTRIBUTING.md` — NEW — human-facing contributor doc: how to set up `uv sync`, run tests, run lint+typecheck, the 400-LOC rule, where stories live, the PR template requirement
- `.github/PULL_REQUEST_TEMPLATE.md` — NEW — checklist forcing each PR to (1) link the story ID, (2) cite at least one `context/<folder>/<file>.md` source, (3) confirm `uv run pytest && uv run ruff check . && uv run mypy packages/aegis_core/src packages/aegis_judges/src` is green locally, (4) confirm no file > 400 LOC
- `.github/ISSUE_TEMPLATE/bug_report.md` — NEW — bug template (matches `docs/architecture.md` § "Repo structure" layout)
- `.github/ISSUE_TEMPLATE/story.md` — NEW — story template (matches `docs/architecture.md` § "Repo structure" layout)

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given CLAUDE.md exists at repo root
When  `test -f CLAUDE.md` runs
Then  exit code is 0

Given CLAUDE.md is required to cite the 400-LOC rule, mypy-strict scope, and context/ citation rule
When  `grep -cE '(400[ -]?LOC|≤ ?400|400 ?lines)' CLAUDE.md` runs
Then  stdout is ≥ "1"
And   `grep -ciE 'mypy.*strict' CLAUDE.md` outputs ≥ "1"
And   `grep -ciE 'context/' CLAUDE.md` outputs ≥ "3"

Given CLAUDE.md must enumerate banned patterns
When  `grep -ciE '(requests|verify=False|unittest\.mock|print\(.*log|try.*except.*pass)' CLAUDE.md` runs
Then  stdout is ≥ "3"

Given CLAUDE.md must pin stack
When  `grep -cE '(Python 3\.13|uv|pydantic|httpx|structlog)' CLAUDE.md` runs
Then  stdout is ≥ "3"

Given CONTRIBUTING.md exists at repo root
When  `test -f CONTRIBUTING.md` runs
Then  exit code is 0

Given CONTRIBUTING.md documents the canonical local-dev commands
When  `grep -cE '(uv sync|uv run pytest|uv run ruff|uv run mypy)' CONTRIBUTING.md` runs
Then  stdout is ≥ "4"

Given .github/PULL_REQUEST_TEMPLATE.md exists
When  `test -f .github/PULL_REQUEST_TEMPLATE.md` runs
Then  exit code is 0

Given PR template forces a story ID + context/ citation
When  `grep -ciE '(story[-_ ]id|story[-_ ]link)' .github/PULL_REQUEST_TEMPLATE.md` runs
Then  stdout is ≥ "1"
And   `grep -ciE 'context/' .github/PULL_REQUEST_TEMPLATE.md` outputs ≥ "1"

Given PR template includes the local green-light command set
When  `grep -ciE '(uv run pytest|uv run ruff|uv run mypy)' .github/PULL_REQUEST_TEMPLATE.md` runs
Then  stdout is ≥ "3"

Given .github/ISSUE_TEMPLATE/ has both templates
When  `ls .github/ISSUE_TEMPLATE/*.md | wc -l` runs
Then  stdout (trimmed) is "2"
```

Every criterion must be checkable by running a command. Prose-only criteria = blocked.

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# 1. All four files present
for f in CLAUDE.md CONTRIBUTING.md .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/bug_report.md .github/ISSUE_TEMPLATE/story.md; do
  test -f "$f" || { echo "missing: $f"; exit 1; }
done
echo "all five files present"

# 2. CLAUDE.md hits all required topics
grep -cE '(400[ -]?LOC|≤ ?400|400 ?lines)' CLAUDE.md
grep -ciE 'mypy.*strict' CLAUDE.md
grep -ciE 'context/' CLAUDE.md
grep -ciE '(requests|verify=False|unittest\.mock|print\(.*log)' CLAUDE.md
grep -cE '(Python 3\.13|uv|pydantic|httpx|structlog)' CLAUDE.md

# 3. CONTRIBUTING.md hits all required local-dev commands
grep -cE '(uv sync|uv run pytest|uv run ruff|uv run mypy)' CONTRIBUTING.md

# 4. PR template has story link + context/ citation + green-light commands
grep -ciE '(story[-_ ]id|story[-_ ]link)' .github/PULL_REQUEST_TEMPLATE.md
grep -ciE 'context/' .github/PULL_REQUEST_TEMPLATE.md
grep -ciE '(uv run pytest|uv run ruff|uv run mypy)' .github/PULL_REQUEST_TEMPLATE.md

# 5. CLAUDE.md is itself under 400 LOC (eat your own dog food)
LOC=$(grep -cvE '^\s*(#|$)' CLAUDE.md)
test "$LOC" -le 400 && echo "CLAUDE.md ≤ 400 LOC ($LOC)"
```

---

## Notes for coding agent

- Per `docs/architecture.md` § "File-level references back into `context/`", every load-bearing claim must cite back into `context/` using the pattern `Per context/<folder>/<file>.md §<section>:`. CLAUDE.md must require this in the PR template — bare assertions without citations get blocked by `sahil-pr-audit`.
- Per `docs/architecture.md` § "Coding standards" hard rules, encode in CLAUDE.md verbatim:
  - rule 1: every source file ≤ 400 LOC (excluding blank lines + pure comments)
  - rule 2: `mypy --strict` clean for `packages/aegis_core/` and `packages/aegis_judges/`
  - rule 3: `ruff` clean monorepo-wide (line-length 100, all rules except E501)
  - rule 4: all tests pass (`uv run pytest` exit 0)
  - rule 5: no real Cisco API credentials in code or fixtures
  - rule 6: no real Splunk credentials in code or fixtures
  - rule 7: no `verify=False` in production code paths
- Per `docs/architecture.md` § "Banned patterns", CLAUDE.md must list and forbid:
  - `requests` library (use `httpx`)
  - `verify=False` in production
  - `print()` for logs (use `structlog`)
  - `unittest.mock` for HTTP (use `respx`)
  - `try/except: pass` (always re-raise as `AegisError` subclass)
  - `# type: ignore` without inline justification
  - `Any` type annotations in `aegis_core` or `aegis_judges`
  - Foundation-Sec used as a classifier (explainer only — ADR-003)
- Per `docs/architecture.md` § "Required external libraries" Context7 library research rule, CLAUDE.md must require: before implementing anything from scratch, the coding agent uses `mcp__context7__resolve-library-id` + `mcp__context7__query-docs` to confirm no existing library solves it.
- Per `docs/architecture.md` § "ADR-009", the 400-LOC rule is enforced by both pre-commit (local) and CI (server). CLAUDE.md should make clear the pre-commit hook + CI gate are the source of truth, not vibe.
- Per `../../../context/HALLUCINATION-AUDIT.md`, CLAUDE.md should warn against the specific historical hallucination patterns (e.g., H-44/H-45 around DefenseClaw Python install — it is a Go binary, integrate by config, do not pip-install).
- Match the architecture doc's tone — concise, declarative, no hedging. CLAUDE.md is read by agents under time pressure; bullet-dense and unambiguous wins.
- Per `docs/architecture.md` § "Repo structure", `.github/ISSUE_TEMPLATE/bug_report.md` and `.github/ISSUE_TEMPLATE/story.md` are the two issue templates expected. Keep both short — a header, 3-5 bullets, no fancy YAML frontmatter.
- The PR template is the contract — every reviewer (human or `sahil-pr-audit`) checks it. Make the checkboxes machine-greppable so CI can later assert on PR body shape.

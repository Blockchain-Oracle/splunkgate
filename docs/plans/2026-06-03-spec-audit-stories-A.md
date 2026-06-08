# Spec Audit — Stories A (EPICs 1, 2, 3, 4)

Auditor: stories batch A
Date: 2026-06-03
Files audited: 21 (EPIC-01 ×8, EPIC-02 ×4, EPIC-03 ×4, EPIC-04 ×5)

## Summary

7 critical findings · 13 minor findings · 1 cross-batch pattern

The 21 stories are uniformly high quality. Format compliance is near-perfect, BDD criteria are virtually all machine-verifiable, file maps are exact, and citations point at real `context/` files. The critical findings cluster around four issues: (1) **scope bleed between cicd-01, cicd-02, cicd-04, skel-01, and skel-04** — multiple stories create the same files (`pyproject.toml`, `.pre-commit-config.yaml`, `__init__.py` stubs, `uv.lock`), (2) **dependency-graph contradictions** between epics-1 and 2 (skel-01 says `Depends on: cicd-01` while cicd-01 creates everything skel-01 also creates), (3) **estimate ≤ 2h compliance** is fine but several are at the ceiling with implausibly large scope, and (4) **a `Status: PENDING` header is missing in zero stories — but the `**Status:** PENDING` line uses inconsistent casing in one place**. Minor findings cover LOC-budget annotations, missing §14 grep checks, off-by-one fixture counts, and one wrong context citation path depth.

## Critical findings (story is unbuildable as written)

- **A-C-01 — story-cicd-01 + story-skel-01 — Massive file-map overlap; cicd-01 creates the entire uv workspace that skel-01 claims to create.**
  - Problem: `story-cicd-01-build-pipeline-python-wheels.md` lines 24-34 already creates `pyproject.toml`, `.python-version`, `uv.lock`, and all four `packages/splunkgate_*/pyproject.toml` + `src/splunkgate_*/__init__.py` stubs. `story-skel-01-uv-workspace-pyproject.md` lines 22-39 then creates the SAME files (`pyproject.toml`, `uv.lock`, `.python-version`, all 4 package `pyproject.toml`s + `__init__.py` stubs, plus eval/). Both are marked NEW. Both run on `Depends on: cicd-01` (skel-01) and `Depends on: None` (cicd-01). cicd-01 will land first per the dispatch queue and skel-01 will then fail because every file already exists. The orchestrator has no way to know which file map "wins."
  - Suggested fix: Re-scope cicd-01 to own ONLY `.github/workflows/ci.yml` + the `build-wheels` and `build-app` jobs. Move every `pyproject.toml` + `__init__.py` + `uv.lock` + `.python-version` creation to skel-01 (which is the natural owner per epic title "Repo skeleton"). Flip the dependency: cicd-01 should depend on skel-01, not the reverse. Then update sprint-status.yaml lines 22-46 to reverse the EPIC-01/EPIC-02 ordering OR have cicd-01 use `UPDATE` markers and reference skel-01 as a dependency.

- **A-C-02 — story-cicd-02 + story-cicd-06 + story-skel-01 — `eval/pyproject.toml` and `eval/src/splunkgate_eval/__init__.py` triple-created.**
  - Problem: cicd-01 lists `eval` as a workspace member in its `pyproject.toml` (note 24). cicd-02 does not create `eval/`. cicd-06 lines 24-26 creates `eval/pyproject.toml`, `eval/src/splunkgate_eval/__init__.py`, `eval/scripts/__init__.py`. skel-01 lines 35-36 also creates `eval/pyproject.toml` + `eval/src/splunkgate_eval/__init__.py`. cicd-01 references `eval` as a workspace member that exists at sync time — but skel-01 (which would create it) depends on cicd-01, and cicd-06 depends on cicd-02 which depends on cicd-01. Same file created by three stories.
  - Suggested fix: Make skel-01 the sole owner of the eval workspace skeleton. Strip `eval/pyproject.toml` + `__init__.py` creation from cicd-06; have cicd-06's file-map mark those as `UPDATE` (add scripts dir + smoke.py to a pre-existing eval package). Strip `eval` workspace listing from cicd-01's `pyproject.toml` (use a placeholder root and let skel-01 add the workspace members).

- **A-C-03 — story-cicd-02 + story-skel-01 — pytest dep declared in two stories with different placement.**
  - Problem: cicd-02 line 24 says it adds `[dependency-groups]` `dev = [pytest, pytest-asyncio, pytest-cov, hypothesis, respx]` to root `pyproject.toml`. skel-01 note line 131 says "If `pytest` is not yet on the workspace, add it as a top-level dev dep ONLY in the root `pyproject.toml` under `[dependency-groups]` `dev`." Both stories may add pytest. skel-01 depends on cicd-01 (not cicd-02) — so when skel-01 lands, pytest is NOT yet there from cicd-02, and skel-01 will add it. Then cicd-02 will try to add an entry that already exists.
  - Suggested fix: skel-01 owns pytest + pytest-asyncio dev-deps (it's the workspace owner). cicd-02 owns only `respx`, `hypothesis`, `pytest-cov` additions, and explicitly UPDATES the existing `[dependency-groups].dev` list.

- **A-C-04 — story-cicd-04 + story-skel-04 — `.pre-commit-config.yaml` double-create + conflicting hook IDs.**
  - Problem: cicd-04 line 23 creates `.pre-commit-config.yaml` (NEW) with a hook id `check-loc` calling `bash .github/scripts/check_loc.sh`. skel-04 line 25 UPDATES `.pre-commit-config.yaml` to add a hook id `check-loc-400` calling `.pre-commit-hooks/check_loc.py` (a different file). Two different scripts (`.sh` and `.py`), two different hook IDs, two different code paths, both purportedly enforcing the same 400-LOC rule. cicd-04's BDD criterion lines 50-55 asserts `id: check-loc` exists; skel-04's lines 59-61 asserts `id: check-loc-400` exists. Both must be true simultaneously.
  - Suggested fix: Pick ONE: either the bash script in `.github/scripts/check_loc.sh` (cicd-03's artifact, reused by cicd-04) OR the Python script in `.pre-commit-hooks/check_loc.py` (skel-04's artifact). Architecture line 376 says `.pre-commit-hooks/check_loc.py` is the canonical name, but cicd-spec.md lines 191-214 codifies the bash script. Reconcile in architecture.md + collapse one of the two stories. Recommend: skel-04 becomes a no-op or is deleted; the bash hook in cicd-04 is canonical. Update sprint-status.yaml dependency `story-skel-04 depends_on: [skel-02, cicd-04]` to remove the duplicate.

- **A-C-05 — story-cicd-04 + story-cicd-03 — fixture filename mismatch + dependency direction wrong.**
  - Problem: cicd-04 line 99 references `tests/fixtures/loc_oversized.py.fixture` (created in cicd-03 per `Depends on:` chain). cicd-04 line 26 references "the fixture from cicd-03". But cicd-03 is the one that creates `loc_oversized.py.fixture` — fine. However cicd-04 ALSO creates `tests/fixtures/pre_commit_violators/has_print.py.fixture` + `has_secret.py.fixture` (lines 26-27), placing them in a DIFFERENT subfolder than cicd-03's `tests/fixtures/loc_oversized.py.fixture`. The verification script in cicd-04 line 99 `cp tests/fixtures/loc_oversized.py.fixture ...` will work only if cicd-03 ran first. sprint-status.yaml confirms `story-cicd-04 depends_on: [story-cicd-03]` — but skel-04 ALSO depends on cicd-04, creating a chain where skel-04 needs cicd-03's fixture under `tests/fixtures/loc_oversized.py.fixture`. This is consistent IF cicd-03's fixture path is fixed. Cross-check: cicd-03 line 26 puts the fixture at `tests/fixtures/loc_oversized.py.fixture` — OK.
  - Suggested fix: This isn't strictly broken, but the shared `tests/fixtures/` directory is owned by NO story. Add an explicit `tests/fixtures/__init__.py` (NEW) line and a `tests/__init__.py` ownership statement to cicd-03. As-is, cicd-03 creates files in a directory that doesn't exist yet in the repo — `cp` will fail. Add `mkdir -p tests/fixtures/` in cicd-03's verification + explicitly NEW the directory marker.

- **A-C-06 — story-cicd-05 + story-app-01 — `splunk_apps/splunkgate_app/default/app.conf` + `README` double-created.**
  - Problem: cicd-05 lines 25-26 creates `splunk_apps/splunkgate_app/README` (Splunkbase-shape README, no extension) and `splunk_apps/splunkgate_app/default/app.conf` (minimal valid config). cicd-05 explicitly notes "EPIC-09 story `story-app-01-app-conf-and-metadata-skeleton.md` owns the real content; this story creates only the stub." But sprint-status.yaml shows `story-app-01-app-conf-and-metadata-skeleton depends_on: []` (no dependency on cicd-05) — so app-01 may run before cicd-05 lands, creating the same files, and the dispatcher cannot serialize them. EPIC-09 ordering says app-01 is sequential within its epic but doesn't list cicd-05 as predecessor.
  - Suggested fix: Add `cicd-05` to `story-app-01-app-conf-and-metadata-skeleton.depends_on` in sprint-status.yaml. OR have cicd-05 NOT create those files and instead skip the AppInspect job until app-01 has landed (gate the workflow on file existence). Recommend the former — cicd-05 needs SOMETHING to inspect, so own the stub there and have app-01 use `UPDATE` markers.

- **A-C-07 — story-skel-02 BDD criterion uses `configparser` against an INI file but mypy.ini fields may not parse correctly.**
  - Problem: skel-02 lines 47-53 BDD: ``c.read('mypy.ini'); print(c.get('mypy-splunkgate_core.*','strict'))``. Section names containing dots (e.g., `[mypy-splunkgate_core.*]`) are valid in mypy's INI, but Python's `configparser` returns the literal string `"True"` not the boolean — that's fine for `print`. However `mypy.ini` allows uppercase True/False, and `configparser.get()` returns `str`, so `assert "True" in stdout` will work. But more critically: the BDD assertion at line 53 uses `c.get('mypy-splunkgate_core.*','strict')` — `configparser` interpolation default would treat `*` as a wildcard char and may raise `InterpolationSyntaxError` on the `%(...)` substitution mechanism. The script should use `configparser.RawConfigParser` to bypass interpolation. Coding agent will hit this and burn 30 min.
  - Suggested fix: Replace the BDD's `configparser` probe with a `grep -E "^\[mypy-splunkgate_core\.\*\]$" mypy.ini` followed by a context-aware check using `awk` or a small inline Python snippet using `configparser.ConfigParser(interpolation=None)`.

## Minor findings (story works but is sub-optimal)

- **A-M-01 — story-cicd-01 line 134 references a tool version pinned in cicd-spec.md but offers no LOC-budget annotations** per the format-spec "Every source file ≤ 400 LOC". Multiple files created (8 small `__init__.py`, 4 `pyproject.toml`, root `pyproject.toml`, `uv.lock`, `.python-version`, CI YAML) — all trivially well under 400. Mention "each ≤ 50 LOC" in the file map for explicit budget compliance.

- **A-M-02 — story-cicd-02 BDD line 60 references `if: ${{ matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges' }}` — that is the CI YAML expression in GitHub Actions syntax, but the BDD then says "verified via `if: ...`" which is prose-only.** Convert to: `grep -q "matrix.package == 'splunkgate_core' || matrix.package == 'splunkgate_judges'" .github/workflows/ci.yml`.

- **A-M-03 — story-cicd-03 fixture creation step (line 115) suggests `python -c "print('x = 1\\n' * 425, end='')"`** but the verification script counts non-blank-non-comment lines via `grep -cvE '^\s*(#|$)'`. `x = 1\n` produces 425 lines, each non-blank and non-comment. That's correct, but the off-by-one issue is that the threshold is `> 400` (strict greater-than per spec line 202), so 401 LOC fails and 400 passes. The fixture uses 425 — fine. The threshold fixture at exactly 400 LOC is correctly described. Just flag explicitly that `wc -l` counts differently from the gate (`wc` counts physical lines, the gate counts non-blank-non-comment). Add a `wc -l` check assertion alongside.

- **A-M-04 — story-cicd-04 line 138 says "use `AKIA` + a fresh random 16-char `[A-Z0-9]` string" but doesn't pin the exact string in the fixture file**, so the verification step (line 113) `cp tests/fixtures/pre_commit_violators/has_secret.py.fixture ...` succeeds. But what's IN the fixture? It must be created with a specific string at fixture-write time. Add explicit content: e.g., `AKIAZ7Q9X4M8VPLBT2RS` (fresh-random pattern that gitleaks v8.21.2 reliably catches).

- **A-M-05 — story-cicd-05 BDD line 44 regex `^splunk-appinspect (4\.[2-9]|[5-9])\.`** — handles 4.2–4.9 and 5.x+ but not 4.10 or 4.20. Use `^splunk-appinspect (4\.([2-9]|[1-9][0-9])|[5-9])\.` for future-proofing.

- **A-M-06 — story-cicd-06 BDD line 81 asserts `"category": "pii"` count is exactly 5** — but the JSON serialization could put it on a single-line array. `grep -c` counts matching LINES not occurrences. If smoke_prompts.jsonl is well-formed JSON-lines (one record per line), this works. Add an explicit assertion that the file has exactly 20 newlines (one per record).

- **A-M-07 — story-cicd-06 BDD lines 54-57 — "stderr contains `NotImplementedError` or `live mode not wired in cicd-06`"** — this is an `OR` predicate; the script must produce one or the other. Recommend tightening to "stderr contains exactly the string `live mode not wired in cicd-06`" so the test is deterministic.

- **A-M-08 — story-cicd-07 line 25 references `verify=False` as an allowlist entry in `.gitleaks.toml`** — but `verify=False` is not a secret pattern gitleaks would match. The carve-out is unnecessary and may suggest scope confusion. Drop it.

- **A-M-09 — story-cicd-08 BDD line 65-67 manual end-to-end sandbox tag-push step is correctly marked manual,** but the BDD criterion as written (line 66 "When the release workflow runs") implies automation. Mark explicitly as `Given/When/Then [manual]` or move entirely to Notes.

- **A-M-10 — story-skel-01 verification step 8 (line 116) `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/ eval/ --include="*.py" | grep -v "test_" | grep -v "_mock.py"`** — there are no .py files yet besides empty `__init__.py` placeholders, so the §14 check is trivially clean. Note this explicitly so future stories don't assume it ran meaningfully.

- **A-M-11 — story-skel-03 BDD line 67 — `grep -ciE '(story[-_ ]id|story[-_ ]link)'` is case-insensitive AND allows three separator characters,** but the actual template just says `story-id` consistently. Tighten to a single canonical phrase.

- **A-M-12 — story-core-01 BDD line 56 ends `print(v.verdict.value)` — exit code 0 required, stdout "BLOCK".** The Python here imports `datetime` from `datetime` AND `UTC` — `from datetime import datetime, UTC` requires Python 3.11+. Repo is 3.13. Fine. But the one-liner is long; recommend a `tests/` fixture file path for re-runnability.

- **A-M-13 — story-judges-04 BDD line 40 "exactly 44"** — 11 rules × 4 severities = 44. Correct. But fixture matrix line 38 references `_fixtures/ai_defense_matrix.json` containing 44 entries. Each entry is one InspectResponse. Issue: an InspectResponse can have MULTIPLE rules (the `rules: list[RuleHit]`). The 44-row matrix is one-rule-per-response; this is a fine convention but should be stated explicitly to avoid the coding agent producing 11-row matrices each with 4-severity-mixed responses. Add: "Each fixture has exactly one RuleHit in `rules[]`."

## Cross-batch observations

1. **The same `.pre-commit-config.yaml` + `pyproject.toml` + 4× `splunkgate_*/pyproject.toml` + `uv.lock` are owned by no fewer than five stories** (cicd-01, cicd-02, cicd-04, skel-01, skel-04). This is the single largest spec-quality issue across the batch. Suggest a 30-min round of consolidation: skel-01 owns the workspace skeleton, cicd-01 owns only CI YAML, cicd-04 owns only the pre-commit config wiring, and all other stories use `UPDATE` markers only. Then re-flip the EPIC-01 vs EPIC-02 dependency direction so skel-01 lands BEFORE cicd-01 — the workspace must exist before CI can sync it.

2. **No story has an explicit LOC-budget annotation on every file in the modification map.** The template (story-template.md line 26) doesn't require it explicitly, but the architecture's 400-LOC hard rule does. Several stories list 5-10 files without per-file budgets. Add as a soft convention: "every NEW file gets `(~Xh budget Y LOC)` annotation."

3. **§14 (no mocks in hot path) grep checks are present in core-01, core-02, core-03, core-04, judges-01, judges-02, judges-04 — but ABSENT from cicd-01..08 and skel-01..04.** That's correct for CI/skeleton stories (they don't ship hot-path code), but flag in PRs why the check is omitted (avoid the auditor flagging it later as missing).

4. **Context citation paths use `../../../context/...` (3 levels up) from stories** in docs/stories/. The actual path from `docs/stories/story-X.md` to `context/` is `../../context/...` (TWO levels up: stories → docs → repo root → context). Several stories use the 3-level form. Cross-check: skel-01 note "Per `docs/architecture.md`" uses no relative path (correct in-tree); but story-cicd-04 note line 142 cites `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md` (3 levels). The relative-path is consistent across many stories but appears to use 3 levels universally — this is correct IF context/ lives at a sibling of the parent of the splunkgate workspace (`/Users/abu/dev/hackathon/splunk/workspace/context/`), but if context/ is at `/Users/abu/dev/hackathon/splunk/workspace/splunkgate/../context/`, the 3-level form is right. The parent confirmed file existence so this is not flagged as broken, but recommend STANDARDIZING and adding a comment in CLAUDE.md explaining the path depth.

5. **Estimates: 21/21 stories ≤ 2h.** No violation. Many are at 1.5–2h which is realistic given the scope.

## Per-story matrix

| Story ID | Format OK? | BDD verifiable? | File-map exact? | Citations cite real files? | Estimate OK? | Critical findings |
|---|---|---|---|---|---|---|
| story-cicd-01-build-pipeline-python-wheels | YES | YES | NO (overlap w/ skel-01) | YES | YES (1.5h) | A-C-01 |
| story-cicd-02-test-pipeline-pytest-respx | YES | YES | NO (overlap w/ cicd-06, skel-01) | YES | YES (1.5h) | A-C-02, A-C-03 |
| story-cicd-03-loc-cap-enforcement | YES | YES | YES | YES | YES (1h) | A-C-05 (minor) |
| story-cicd-04-pre-commit-hooks | YES | YES | NO (overlap w/ skel-04) | YES | YES (1h) | A-C-04 |
| story-cicd-05-appinspect-gate | YES | YES | NO (overlap w/ app-01) | YES | YES (1.5h) | A-C-06 |
| story-cicd-06-eval-smoke-job | YES | YES | NO (overlap w/ skel-01) | YES | YES (1.5h) | A-C-02 |
| story-cicd-07-security-scan-pipeline | YES | YES | YES | YES | YES (1.5h) | none |
| story-cicd-08-release-pipeline-signed | YES | YES | YES | YES | YES (1.5h) | none |
| story-skel-01-uv-workspace-pyproject | YES | YES | NO (overlap w/ cicd-01) | YES | YES (1.5h) | A-C-01, A-C-02 |
| story-skel-02-ruff-mypy-config | YES | partially (A-C-07) | YES | YES | YES (1.5h) | A-C-07 |
| story-skel-03-claude-md-and-contribution-conventions | YES | YES | YES | YES | YES (1.5h) | none |
| story-skel-04-loc-check-script-and-pre-commit | YES | YES | NO (overlap w/ cicd-04) | YES | YES (2h ceiling) | A-C-04 |
| story-core-01-verdict-pydantic-types | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-core-02-otel-evaluation-event-emitter | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-core-03-error-model-and-trace-propagation | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-core-04-structlog-config-and-conventions | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-judges-01-ai-defense-request-response-models | YES | YES | YES | YES | YES (1.5h) | none |
| story-judges-02-ai-defense-httpx-client-with-retries | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-judges-03-ai-defense-circuit-breaker-tenacity | YES | YES | YES | YES | YES (2h ceiling) | none |
| story-judges-04-ai-defense-mock-respx-fixtures | YES | YES | YES | YES | YES (1.5h) | none |
| story-judges-05-ai-defense-end-to-end-integration-test | YES | YES | YES | YES | YES (2h ceiling) | none |

## Sprint-status.yaml dependency cross-check

All 21 stories have `Depends on:` headers matching sprint-status.yaml entries EXACTLY:

- cicd-01 → `[]` ✓
- cicd-02 → `[cicd-01]` ✓
- cicd-03 → `[cicd-01]` ✓
- cicd-04 → `[cicd-03]` ✓
- cicd-05 → `[cicd-01]` ✓
- cicd-06 → `[cicd-02]` ✓
- cicd-07 → `[]` ✓
- cicd-08 → `[cicd-01]` ✓
- skel-01 → `[cicd-01]` ✓ (but see A-C-01 — direction is wrong)
- skel-02 → `[skel-01]` ✓
- skel-03 → `[skel-01]` ✓
- skel-04 → `[skel-02, cicd-04]` ✓
- core-01 → `[skel-02]` ✓
- core-02 → `[core-01]` ✓
- core-03 → `[core-01]` ✓
- core-04 → `[skel-02]` ✓
- judges-01 → `[core-01]` ✓
- judges-02 → `[judges-01]` ✓
- judges-03 → `[judges-02]` ✓
- judges-04 → `[judges-01]` ✓
- judges-05 → `[judges-03, judges-04]` ✓

No `Depends on:` declaration drift between stories and sprint-status.yaml. The dependency GRAPH itself contains the A-C-01 issue (skel-01 should NOT depend on cicd-01 — the reverse is true).

## Spec-content correctness — Does each story implement a real piece of the anchor doc?

- **EPIC-01 (cicd-spec.md):** All 8 stories implement the spec faithfully. cicd-01 owns `lint` + `typecheck` + `build-wheels` + `build-app` (spec lines 67-92, 153-187). cicd-02 owns `test` matrix (spec lines 103-119). cicd-03 owns `loc-cap` (spec lines 94-101 + 191-214). cicd-04 owns pre-commit config (spec lines 402-442). cicd-05 owns `appinspect` (spec lines 120-139). cicd-06 owns `eval-smoke` (spec lines 141-151). cicd-07 owns `security.yml` (spec lines 352-398). cicd-08 owns `release.yml` (spec lines 285-332). No gaps in cicd-spec.md coverage.

- **EPIC-02 (architecture.md "Repo structure" + "Coding standards"):** skel-01 covers workspace + Python pin. skel-02 covers ruff + mypy hard rules 2-3. skel-03 covers CLAUDE.md + PR template. skel-04 covers local pre-commit LOC enforcement (hard rule 1). One gap: the soft rule "All public functions get a docstring (numpy/Google style)" (architecture line 192) is mentioned in skel-02 notes but no story enforces it via a tool. Recommend: add a `D` ruff rule subset to skel-02's BDD criteria (skel-02 already enables ruff `select=["ALL"]`, which pulls in `D` — but the per-file-ignores for tests omit `D`, which is correct; the actual issue is that `D` rules will fire on every undocumented function in `splunkgate_core` once those land — that's the intended behavior).

- **EPIC-03 (architecture.md "API schemas"):** core-01 implements `Verdict` + `Severity` + `VerdictLabel` + `RuleHit` exactly per spec lines 254-282. core-02 implements OTel emission exactly per spec lines 287-306. core-03 implements the error hierarchy (architecture soft rule "subclass SplunkGateError"). core-04 implements structlog conventions (architecture soft rule). No gaps.

- **EPIC-04 (`context/07-cisco-stack/01-ai-defense-deep.md`):** judges-01 implements request/response types with `rules` field (not `triggered_rules`) per HALLUCINATION-AUDIT H-37. judges-02 implements httpx client + regional routing + auth header verbatim. judges-03 implements circuit breaker. judges-04 implements mock + env-var toggle (architecture ADR-006). judges-05 implements end-to-end integration test + verdict mapping. No gaps. One subtle inconsistency: judges-01 defines `Severity` in `ai_defense_types.py` and notes "Re-use `splunkgate_core.verdict.Severity` if it matches; otherwise define `Severity` here mirroring the AI Defense response" (line 118). This SHOULD be a hard "always re-use" given core-01 already defines the canonical Severity enum with NONE_SEVERITY. Recommend tightening judges-01's note to require re-use of `splunkgate_core.verdict.Severity` unconditionally.

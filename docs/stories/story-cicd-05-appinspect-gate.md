# Story — Splunk AppInspect gate: runner + parser; error-severity findings block PR

**ID:** story-cicd-05-appinspect-gate
**Epic:** EPIC-01 — CI/CD foundation
**Depends on:** story-cicd-01-build-pipeline-python-wheels
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** coding agent landing changes to `splunk_apps/aegis_app/`
**I want to** the `appinspect` CI job run `splunk-appinspect 4.2.1+` against the app with cloud + self-service + appapproval tags and fail the PR if any `error`-severity finding appears
**So that** we never merge an app that would be rejected at Splunkbase submission, and the manual-check exception pattern from the CIMplicity 2025 winner (`.appinspect.expect.yaml`) is wired from day one

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `.github/workflows/ci.yml` — UPDATE — append the `appinspect` job (and the `build-app` job's `needs: [appinspect]` plumbing). Copy verbatim from `docs/cicd-spec.md` § "Concrete YAML skeleton" lines 120-139. Tags pinned to `cloud`, `self-service`, `appapproval` per spec line 129.
- `.github/scripts/parse_appinspect.py` — NEW — Python script (~80-120 LOC, well under cap) that takes one argument `appinspect-report.json`, parses the JSON, counts entries with `result == "error"` (case-insensitive); exits 0 if zero errors, exits 1 if any errors. Emits `::error file=splunk_apps/aegis_app/...::<check_name>: <message>` GitHub annotation per error finding. Excludes findings already listed in `splunk_apps/aegis_app/.appinspect.expect.yaml` (verbatim string match on the `check_name` field). Uses only stdlib (`json`, `sys`, `pathlib`, `yaml` is acceptable since `pyyaml` is a uv-managed dep) — no `pydantic`, no network calls.
- `splunk_apps/aegis_app/README` — NEW — minimal Splunkbase-required README (file MUST be named `README` with no extension per Splunkbase rules, not `README.md`). Single line: `Aegis — agentic-AI safety verdict surface for Splunk`. EPIC-09 story `story-app-01-app-conf-and-metadata-skeleton.md` owns the real content; this story creates only the stub so AppInspect has something to inspect.
- `splunk_apps/aegis_app/default/app.conf` — NEW — minimal valid `app.conf` (`[install]` `is_configured = true`; `[package]` `id = aegis_app`; `[ui]` `is_visible = false`; `[launcher]` `version = 0.0.0` `description = Aegis` `author = aegis-team`). Sufficient to pass `appinspect inspect` without `error`-severity findings on the empty shell. Real content lands in EPIC-09.
- `splunk_apps/aegis_app/.appinspect.expect.yaml` — NEW — empty YAML file with header comment `# Manual-check exceptions list. Mirrors CIMplicity AI 2025 winner pattern. Per context/11-prior-art/01-build-a-thon-2025-deep-read.md.` The file MUST exist (parser script depends on it) but starts empty. EPIC-12 story `story-app-11-appinspect-expect-yaml-and-manual-checks.md` populates it.
- `tests/test_parse_appinspect.py` — NEW — pytest module with minimum 6 test cases: (a) zero findings → exit 0; (b) one error finding → exit 1; (c) one warning finding (not error) → exit 0; (d) multiple errors → exit 1 with one annotation per error; (e) error finding listed in `.appinspect.expect.yaml` → suppressed, exit 0; (f) malformed JSON → exit 1 with stderr explanation.
- `tests/fixtures/appinspect/zero_findings.json` — NEW — sample AppInspect JSON output with zero error-severity entries
- `tests/fixtures/appinspect/one_error.json` — NEW — sample with one error finding
- `tests/fixtures/appinspect/mixed.json` — NEW — sample with one error and two warnings
- `tests/fixtures/appinspect/in_expect_list.json` — NEW — sample with one error whose `check_name` is in the expect file

The coding agent must NOT modify files outside this map without re-checking CLAUDE.md.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given `splunk-appinspect` v4.2.1+ is installed via `uv sync --frozen`
When  `uv run splunk-appinspect --version` runs
Then  exit code is 0
And   stdout matches `^splunk-appinspect (4\.[2-9]|[5-9])\.`

Given the minimal `splunk_apps/aegis_app/` shell exists (app.conf + README + .appinspect.expect.yaml)
When  `uv run splunk-appinspect inspect splunk_apps/aegis_app/ --output-file appinspect-report.json --mode test --included-tags cloud --included-tags self-service --included-tags appapproval` runs
Then  exit code is 0 (the tool itself succeeds — inspecting findings is the parser's job)
And   `appinspect-report.json` exists and is valid JSON

Given the zero-findings fixture is passed to the parser
When  `uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/zero_findings.json` runs
Then  exit code is 0
And   stdout contains `AppInspect passed (no error-severity findings)`

Given the one-error fixture is passed to the parser
When  `uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/one_error.json` runs
Then  exit code is 1
And   stdout or stderr contains `::error`

Given the mixed fixture (1 error + 2 warnings) is passed
When  the parser runs
Then  exit code is 1
And   `::error` annotation appears exactly 1 time (warnings do not produce annotations)

Given the in_expect_list fixture is passed and `.appinspect.expect.yaml` contains the matching `check_name`
When  the parser runs
Then  exit code is 0 (suppressed)

Given `uv run pytest tests/test_parse_appinspect.py` runs
When  the run completes
Then  exit code is 0
And   stdout contains `6 passed` (the 6 BDD scenarios above mapped to test cases)

Given `wc -l .github/scripts/parse_appinspect.py | awk '{print $1}'` runs
When  the output is checked
Then  the value is < 400 (file under cap)

Given the `appinspect` job runs on GitHub Actions
When  the workflow completes on a clean PR
Then  the job is green
And   the `appinspect-report.json` artifact is uploaded
```

---

## Shell verification

The coding agent runs this end-to-end locally before opening a PR:

```bash
set -euo pipefail

# 1. AppInspect installed at 4.2.1+
uv sync --frozen
uv run splunk-appinspect --version | grep -E '^splunk-appinspect (4\.[2-9]|[5-9])\.'

# 2. Shell app passes AppInspect
uv run splunk-appinspect inspect splunk_apps/aegis_app/ \
  --output-file /tmp/appinspect-report.json \
  --mode test \
  --included-tags cloud --included-tags self-service --included-tags appapproval
test -s /tmp/appinspect-report.json
python -c "import json; json.load(open('/tmp/appinspect-report.json'))"

# 3. Parser script exit codes correct for each fixture
uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/zero_findings.json
if uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/one_error.json; then
  echo "FAIL: parser passed an error finding"; exit 1
fi
if uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/mixed.json; then
  echo "FAIL: parser passed a mixed finding set"; exit 1
fi
uv run python .github/scripts/parse_appinspect.py tests/fixtures/appinspect/in_expect_list.json

# 4. Pytest covers all 6 scenarios
uv run pytest tests/test_parse_appinspect.py -v
uv run pytest tests/test_parse_appinspect.py -q | grep -q '6 passed'

# 5. LOC under cap
test "$(grep -cvE '^\s*(#|$)' .github/scripts/parse_appinspect.py)" -lt 400

# 6. CI YAML wires the job
grep -q 'appinspect:' .github/workflows/ci.yml
grep -q 'parse_appinspect.py' .github/workflows/ci.yml

# 7. Push and verify
git push origin HEAD
gh run watch --exit-status
```

All blocks must exit 0.

---

## Notes for coding agent

- Per `../../../context/05-splunk-core/09-appinspect.md`, AppInspect 4.2.1+ is required for Splunkbase submission and Splunk Cloud private-app install. The version pin in `docs/architecture.md` § "Stack (locked)" is a floor — never downgrade to 4.1.x even if a dep complains.
- The three `--included-tags` (`cloud`, `self-service`, `appapproval`) are spec-mandated (`docs/cicd-spec.md` line 129) because the Aegis app targets Splunk Cloud (cloud tag), self-install (self-service tag), and eventual Splunkbase listing (appapproval tag). Removing any tag relaxes the gate.
- Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md`, CIMplicity AI 2025 winner shipped a `.appinspect.expect.yaml` listing 25 manual-checks they had accepted; we mirror this convention. The empty stub in this story is the placeholder — EPIC-12 fills it.
- The parser MUST distinguish `result: error` from `result: warning` and `result: manual_check`. AppInspect JSON output structure: top-level `groups[].checks[]` each has `result` and `messages[]`. The parser walks the tree and counts `result == "error"` per check. Reference: `splunk-appinspect inspect --output-format json --help` for the schema, or inspect a real report at runtime to confirm the field names.
- The `.appinspect.expect.yaml` schema for now: top-level `accepted_errors:` list of strings where each string is a `check_name`. Exact match on `check_name`. EPIC-12 may extend the schema (e.g., add `justification` per entry); the parser must tolerate both string-list and string-keyed-object forms (use `isinstance(entry, str) else entry["check_name"]`).
- Per ADR-008 (`docs/architecture.md` § "Architecture decisions"), the app is Classic Simple XML wrapping Dashboard Studio v2 JSON-in-XML. AppInspect inspects the wrapping XML; the inner JSON is parsed by Splunk at render time. No special AppInspect config needed for this.
- Malformed JSON handling (scenario f): the parser uses `try: json.load(...) except json.JSONDecodeError as e: print(f"::error::malformed AppInspect JSON: {e}", file=sys.stderr); sys.exit(1)`. Do not swallow the exception silently.
- The minimal `app.conf` stanzas above are sufficient to avoid AppInspect erroring on missing required fields. Per `../../../context/05-splunk-core/08-app-packaging-and-conf-files.md`, `[launcher]` `version`, `description`, `author` are required; `[package]` `id` matches the app dir name; `[ui]` `is_visible` controls whether the app shows in Splunk's nav (false until EPIC-09 ships dashboards).
- The parser file budget is ~80-120 LOC; if it grows past 300, split into `parse_appinspect.py` (CLI entry) + `appinspect_parser.py` (logic module) and re-verify both <400 LOC.
- Per `docs/cicd-spec.md` § "Failure mode handling" line 494, warning-severity findings get LISTED in `.appinspect.expect.yaml` as accepted — but this story keeps the parser strict on `error` severity only. EPIC-12 may extend the parser to also surface warnings as PR comments (non-blocking).

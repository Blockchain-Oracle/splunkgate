# Story — .appinspect.expect.yaml + .appinspect.manualcheck.yaml mirroring CIMplicity's 25-check pattern

**ID:** story-app-11-appinspect-expect-yaml-and-manual-checks
**Epic:** EPIC-12 — AppInspect hardening
**Depends on:** story-app-10-app-vision-loop-validation
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Splunk staff judge skimming Aegis's `splunk_apps/aegis_app/` for the standard "is this Splunkbase-ready?" signals
**I want to** see a `.appinspect.expect.yaml` for justified-error suppressions and a `.appinspect.manualcheck.yaml` enumerating the manual-review items, mirroring the CIMplicity AI 2025 winner's exact pattern — and a CI invocation of `splunk-appinspect inspect ... --included-tags cloud` that produces zero error-severity findings
**So that** the app passes the AppInspect gate cleanly the first time it's submitted to Splunkbase, and Splunk staff judges pattern-match the file pair as "this team knows how to ship a real app"

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `splunk_apps/aegis_app/.appinspect.expect.yaml` — NEW — verbatim CIMplicity-style structure: for each suppressed error-severity finding, a 2-space-indented top-level key (the check name) with a single `comment: '<justification string>'`. At a minimum, mirror CIMplicity's verbatim entry for `check_for_binary_files_without_source_code` IF Aegis ships any binary blobs (it should not — story-app-01 banned `bin/` Python — so this check should NOT appear unless we ship icons that trip the AppInspect heuristic). The file's primary intended audience is Splunk staff reviewers; the secondary audience is the CI gate that whitelists each entry as `expected` rather than `failed`. Include a top-of-file comment block with `# Aegis AppInspect expected findings — every entry has a verifiable justification.`
- `splunk_apps/aegis_app/.appinspect.manualcheck.yaml` — NEW — mirrors CIMplicity's `.appinspect.manualcheck.yaml` 25-check verbatim list per `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml`. Every entry is `check_name: { comment: 'Manual check' }`. The 25 entries are: `check_for_console_log_injection_in_javascript`, `check_for_iframe_in_javascript`, `check_for_insecure_http_request_in_javascript`, `check_for_remote_code_execution_in_javascript`, `check_for_builtin_functions`, `check_for_data_compression_and_archiving`, `check_for_file_and_directory_access`, `check_for_generic_operating_system_services`, `check_for_plain_text_credentials_in_python`, `check_for_environment_variable_use_in_python`, `check_for_insecure_http_calls_in_python`, `check_for_secret_disclosure`, `check_for_supported_tls`, `check_for_executable_flag`, `check_for_binary_files_without_source_code`, `check_for_importing_modules`, `check_all_python_files_are_well_formed`, `check_for_shell`, `check_for_optional_operating_system_services`, `check_python_untrusted_xml_functions`, `check_for_data_persistence`, `check_built_in_import_function`, `check_for_hidden_python_files`, `check_for_python_runtime_services`, `check_for_interprocess_communication_and_networking`. Exact order preserved from `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml`.
- `splunk_apps/aegis_app/.appinspect.warnings.md` — NEW — markdown document enumerating every `warning`-severity finding from a local AppInspect run with an explicit justification or remediation note. Per the spec rule "document warning-severity findings explicitly," this gives staff reviewers a single audit document instead of buried inline comments. Each warning entry: `## <check_name>` header + paragraph justification + cross-reference to the `context/` doc that grounds the decision.
- `splunk_apps/aegis_app/scripts/run_appinspect.sh` — NEW — bash script: installs `splunk-appinspect` via `uv run`, runs `splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud --excluded-tags manual --output-file appinspect-report.json --data-format json`, then runs a Python post-processor against `appinspect-report.json` that asserts zero `error`-severity findings (warnings tolerated, manual-checks tolerated). Exit code 1 on any error-severity finding.
- `splunk_apps/aegis_app/scripts/_appinspect_postprocess.py` — NEW — Python script invoked from `run_appinspect.sh`. Reads `appinspect-report.json`, walks `reports → groups → checks`, separates findings by `result` (`success`, `failure`, `error`, `warning`, `manual_check`, `not_applicable`, `skipped`), prints a summary table (count per result), and exits 1 if any check has `result="error"` AND is NOT listed in `.appinspect.expect.yaml`. Also writes a human-readable summary to `appinspect-summary.txt`.
- `splunk_apps/aegis_app/tests/test_appinspect_yaml_files.py` — NEW — ≥ 12 tests: both YAML files parse via `yaml.safe_load`; `.appinspect.manualcheck.yaml` contains exactly 25 keys (matches CIMplicity's count); the set of 25 keys equals the CIMplicity verbatim set (load `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml` and diff key sets); every entry has a `comment` field; every comment value is a non-empty string; `.appinspect.expect.yaml` is YAML-valid (may be empty if no suppressions); the bash script is executable (`stat -c "%a"` shows `+x`); `_appinspect_postprocess.py` exits 0 on a fixture report with no errors; exits 1 on a fixture report with one error finding; properly handles the fixture report's `not_applicable` and `manual_check` cases without erroring.
- `splunk_apps/aegis_app/tests/fixtures/appinspect_clean_report.json` — NEW — small fixture: a real AppInspect report shape with one `success`, one `manual_check`, one `not_applicable`, one `warning` (zero errors); used to assert the postprocessor passes.
- `splunk_apps/aegis_app/tests/fixtures/appinspect_error_report.json` — NEW — fixture with one `error`-severity finding (with check name NOT in `.appinspect.expect.yaml`); used to assert the postprocessor fails.

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given splunk_apps/aegis_app/.appinspect.manualcheck.yaml exists
When  `python -c "import yaml; d=yaml.safe_load(open('splunk_apps/aegis_app/.appinspect.manualcheck.yaml')); print(len(d))"` runs
Then  the output is exactly "25"

Given splunk_apps/aegis_app/.appinspect.manualcheck.yaml
When  the set of check names is collected
Then  it equals the set of check names in `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml` (verbatim CIMplicity 25-check pattern)

Given splunk_apps/aegis_app/.appinspect.manualcheck.yaml
When  every key's value is inspected
Then  every value has a `comment` field equal to "Manual check"

Given splunk_apps/aegis_app/.appinspect.expect.yaml exists (possibly empty)
When  `python -c "import yaml; print(type(yaml.safe_load(open('splunk_apps/aegis_app/.appinspect.expect.yaml'))).__name__)"` runs
Then  the output is one of "dict", "NoneType" (valid empty YAML)

Given splunk_apps/aegis_app/scripts/run_appinspect.sh
When  `stat -c "%a" splunk_apps/aegis_app/scripts/run_appinspect.sh` runs (or equivalent on macOS: `stat -f "%A"`)
Then  the permission mode is 755 (executable)

Given splunk-appinspect 4.2.1+ is installed
When  `bash splunk_apps/aegis_app/scripts/run_appinspect.sh` runs
Then  exit code is 0
And   appinspect-report.json is produced
And   no check has result="error" outside of those listed in .appinspect.expect.yaml

Given the fixture splunk_apps/aegis_app/tests/fixtures/appinspect_clean_report.json
When  `uv run python splunk_apps/aegis_app/scripts/_appinspect_postprocess.py splunk_apps/aegis_app/tests/fixtures/appinspect_clean_report.json` runs
Then  exit code is 0

Given the fixture splunk_apps/aegis_app/tests/fixtures/appinspect_error_report.json
When  `uv run python splunk_apps/aegis_app/scripts/_appinspect_postprocess.py splunk_apps/aegis_app/tests/fixtures/appinspect_error_report.json` runs
Then  exit code is 1

Given `uv run pytest splunk_apps/aegis_app/tests/test_appinspect_yaml_files.py -v`
When  it runs
Then  >= 12 tests pass and 0 fail

Given splunk_apps/aegis_app/.appinspect.warnings.md
When  it is read
Then  the file is non-empty
And   every `## ` header is followed by at least one prose line of justification

Given every modified or new file
When  `wc -l` is run
Then  each file is <= 400 LOC
```

---

## Shell verification

The coding agent runs this end-to-end locally to confirm the story is done before opening a PR:

```bash
set -euo pipefail

# 1. Both YAML files exist and parse
test -f splunk_apps/aegis_app/.appinspect.expect.yaml
test -f splunk_apps/aegis_app/.appinspect.manualcheck.yaml
uv run python -c "import yaml; yaml.safe_load(open('splunk_apps/aegis_app/.appinspect.expect.yaml')); yaml.safe_load(open('splunk_apps/aegis_app/.appinspect.manualcheck.yaml'))"

# 2. Manualcheck has exactly 25 entries
n=$(uv run python -c "import yaml; print(len(yaml.safe_load(open('splunk_apps/aegis_app/.appinspect.manualcheck.yaml'))))")
[ "$n" -eq 25 ] || { echo "FAIL: expected 25 manual checks, got $n"; exit 1; }

# 3. The 25 keys equal the CIMplicity verbatim set
uv run python - <<'PY'
import yaml
ours = set(yaml.safe_load(open("splunk_apps/aegis_app/.appinspect.manualcheck.yaml")).keys())
ref = set(yaml.safe_load(open("../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml")).keys())
missing = ref - ours
extra = ours - ref
assert not missing and not extra, f"missing: {missing}; extra: {extra}"
print("OK")
PY

# 4. Every comment is "Manual check"
uv run python - <<'PY'
import yaml
d = yaml.safe_load(open("splunk_apps/aegis_app/.appinspect.manualcheck.yaml"))
for k, v in d.items():
    assert v.get("comment") == "Manual check", f"{k}: {v}"
print("OK")
PY

# 5. run_appinspect.sh is executable + runs cleanly
chmod +x splunk_apps/aegis_app/scripts/run_appinspect.sh
test -x splunk_apps/aegis_app/scripts/run_appinspect.sh
bash splunk_apps/aegis_app/scripts/run_appinspect.sh

# 6. Postprocessor passes on clean fixture, fails on error fixture
uv run python splunk_apps/aegis_app/scripts/_appinspect_postprocess.py splunk_apps/aegis_app/tests/fixtures/appinspect_clean_report.json
set +e
uv run python splunk_apps/aegis_app/scripts/_appinspect_postprocess.py splunk_apps/aegis_app/tests/fixtures/appinspect_error_report.json
rc=$?
set -e
[ "$rc" -eq 1 ] || { echo "FAIL: postprocessor should exit 1 on error fixture, got $rc"; exit 1; }

# 7. Warnings markdown documents every warning-severity finding
test -s splunk_apps/aegis_app/.appinspect.warnings.md   # non-empty
grep -qE '^## ' splunk_apps/aegis_app/.appinspect.warnings.md   # has at least one ## section

# 8. Tests pass
uv run pytest splunk_apps/aegis_app/tests/test_appinspect_yaml_files.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 12

# 9. 400-LOC cap
for f in \
  splunk_apps/aegis_app/.appinspect.expect.yaml \
  splunk_apps/aegis_app/.appinspect.manualcheck.yaml \
  splunk_apps/aegis_app/.appinspect.warnings.md \
  splunk_apps/aegis_app/scripts/run_appinspect.sh \
  splunk_apps/aegis_app/scripts/_appinspect_postprocess.py \
  splunk_apps/aegis_app/tests/test_appinspect_yaml_files.py; do
  lines=$(wc -l < "$f")
  [ "$lines" -gt 400 ] && { echo "FAIL: $f has $lines LOC"; exit 1; }
done
echo "ALL CHECKS PASS"
```

---

## Notes for coding agent

- **Per `../../../context/11-prior-art/01-build-a-thon-2025-deep-read.md` §1 (CIMplicity AI 2025 winner)**, CIMplicity's `.appinspect.manualcheck.yaml` flags 25 manual checks acknowledged for AppInspect — mirror that pattern verbatim. The deep-read doc states explicitly: *"`.appinspect.manualcheck.yaml` flags 25 manual checks acknowledged for AppInspect (lines 1-51) including `check_for_remote_code_execution_in_javascript`, `check_for_plain_text_credentials_in_python`, `check_for_secret_disclosure`, `check_python_untrusted_xml_functions`, `check_for_supported_tls`, etc. — i.e. the author manually waived two-dozen automated checks rather than rewriting code."* The 25-check list is the precedent pattern — Splunk staff judges recognize it.
- **Per `../../../context/05-splunk-core/09-appinspect.md` § "What the checks actually look for — verbatim from a real failing app"**, the cleanest source of "what AppInspect actually catches" is `../inspiration/cimplicity-ai-app/.appinspect.manualcheck.yaml` — copy its 25 entries verbatim, in the same order. The acceptance criterion explicitly diffs our YAML against that file.
- **Per `../../../context/05-splunk-core/09-appinspect.md` § "`.appinspect.expect.yaml` — suppression with justification"**, every suppressed finding needs a justification comment. Our Aegis app should ship **zero binary files** (DNS Guard pattern, per ADR-008) and **zero Python in `bin/`** (per story-app-01) — so the `.expect.yaml` should be **empty or near-empty**. If story-app-10 (vision validation) shipped icon PNGs that trip a binary-file check, suppress only those with an explicit comment.
- **Per `../../../context/05-splunk-core/09-appinspect.md` § "Running it yourself"**, the canonical invocation is:
  ```bash
  splunk-appinspect inspect splunk_apps/aegis_app/ --mode test --included-tags cloud --excluded-tags manual --output-file appinspect-report.json --data-format json
  ```
  Use this verbatim in `run_appinspect.sh`. The `--excluded-tags manual` skips the items we acknowledge via `.appinspect.manualcheck.yaml` — they don't fail the build, they're flagged for human review at submission time.
- **Per `docs/architecture.md` § "Splunk app validator"** + `../../../context/05-splunk-core/09-appinspect.md`: target version is `splunk-appinspect 4.2.1+`. Verify the installed version is `>= 4.2.1` in the bash script: `installed=$(uv run splunk-appinspect --version | awk '{print $2}'); python -c "from packaging.version import Version; assert Version('$installed') >= Version('4.2.1')"`. Hard-fail if older.
- **Per `../../../context/05-splunk-core/09-appinspect.md` § "Common failure modes for AI-calling Splunk apps"**: the 7 common failure modes are documented — the Aegis app design avoids most of them by construction (no outbound HTTP from `bin/`, no `bin/` Python at all, no `subprocess`). If story-app-10 broke any of these conventions, document the deviation in `.appinspect.warnings.md`.
- **Per CIMplicity verbatim `.appinspect.expect.yaml`** (mirrored from `../inspiration/cimplicity-ai-app/.appinspect.expect.yaml`):
  ```yaml
    check_for_binary_files_without_source_code:
      comment: 'bin/_lsprof.cpython-39-x86_64-linux-gnu.so is usually part of Python distro but not within Splunk and is required by this app'
  ```
  We do NOT mirror this verbatim — we don't ship `.so` files. Our `.expect.yaml` may be entirely empty (just `# Aegis AppInspect expected findings — none currently suppressed.` as a comment block). If a future story adds a binary, append an entry with a per-file justification.
- **Indentation**: CIMplicity's YAML files use **2-space leading indent on top-level keys** (look at the raw file — `  check_for_console_log_injection_in_javascript:` starts with two spaces). This is non-standard YAML formatting but it's what Splunk's tooling expects per the file extension convention. Preserve that exact whitespace. `yaml.safe_load` reads it the same way; the diff is purely cosmetic, but reviewers pattern-match the indentation.
- **The 2 fixture JSON files**: minimal AppInspect report shape per the actual schema (look at a real `splunk-appinspect inspect ... --data-format json` output to get the shape). At minimum: `{"reports": [{"groups": [{"checks": [{"name": "...", "result": "success" | "error" | ...}]}]}]}`. Real reports include many more fields (descriptions, messages, code locations); fixtures need only the fields the postprocessor reads.
- **The `.appinspect.warnings.md` file**: per the spec rule, document warning-severity findings explicitly. Run AppInspect locally first, harvest the warning entries, and write one `## <check_name>` section per warning with a 2–3 sentence justification or remediation note. If there are zero warnings, the file should say so explicitly: `# AppInspect Warnings\n\nNo warning-severity findings as of last run (date: YYYY-MM-DD).`
- **CI gate** (per `docs/cicd-spec.md` and story-cicd-05-appinspect-gate): the `run_appinspect.sh` script is what CI invokes. Exit code 1 → red build. The postprocessor is the bridge between AppInspect's JSON output and the pass/fail decision.
- **Per `../../../context/05-splunk-core/09-appinspect.md` § "Manual review (the human gate)"**: post-automated review, a human Splunk reviewer reads every `.expect.yaml` justification + verifies network destinations + verifies credential handling. Our `.expect.yaml` justifications must be specific enough that a reviewer doesn't need to read source code to understand the rationale.
- Estimate breakdown: ~30 min copy CIMplicity manualcheck.yaml verbatim + verify ordering, ~30 min bash script + postprocessor + fixtures, ~30 min run AppInspect locally + write warnings.md, ~30 min tests + verification.

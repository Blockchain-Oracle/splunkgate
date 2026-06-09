"""End-to-end tests for `.github/scripts/parse_appinspect.py`.

Each test invokes the script as a subprocess so the assertions cover the
real CLI contract (exit code, stdout, stderr) rather than internal function
shapes. The CLI contract is what `.github/workflows/ci.yml` depends on.

BDD coverage map (from docs/stories/story-cicd-05-appinspect-gate.md L43-72):
  (a) zero findings → exit 0                         → test_zero_findings_exit_zero
  (b) one error finding → exit 1                     → test_one_error_exit_one
  (c) one warning (no error) → exit 0                → test_zero_findings_exit_zero
                                                        (zero_findings.json includes a warning)
  (d) multiple errors → exit 1 + one annotation/each → test_mixed_one_error_one_annotation
                                                        + test_multiple_errors_one_annotation_each
  (e) error suppressed via expect file → exit 0      → test_in_expect_list_suppressed
  (f) malformed JSON → exit 1 with stderr msg        → test_malformed_json_exit_one
  + LOC-cap floor (spec L75-77)                      → test_parser_loc_under_cap
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PARSER = REPO_ROOT / ".github" / "scripts" / "parse_appinspect.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "appinspect"


def run_parser(report: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Invoke the parser as a subprocess and return the completed process."""
    cmd = [sys.executable, str(PARSER), str(report), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)


def test_parser_script_exists() -> None:
    assert PARSER.is_file(), f"parser script missing at {PARSER}"


def test_zero_findings_exit_zero() -> None:
    """BDD (a)+(c): a report with no error-severity findings exits 0."""
    result = run_parser(FIXTURES / "zero_findings.json")
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "AppInspect passed" in result.stdout
    # Warning + manual_check entries must NOT produce annotations.
    assert "::error" not in result.stdout
    assert "::error" not in result.stderr


def test_one_error_exit_one() -> None:
    """BDD (b): a single error-severity finding exits 1 with one annotation."""
    result = run_parser(FIXTURES / "one_error.json")
    assert result.returncode == 1
    assert result.stdout.count("::error file=splunk_apps/splunkgate_app/::") == 1
    assert "check_app_does_not_use_disallowed_python_modules" in result.stdout
    assert "1 error-severity finding" in result.stderr


def test_mixed_one_error_one_annotation() -> None:
    """BDD (d) variant: 1 error + 2 warnings → exit 1, exactly 1 annotation."""
    result = run_parser(FIXTURES / "mixed.json")
    assert result.returncode == 1
    annotations = [line for line in result.stdout.splitlines() if line.startswith("::error file=")]
    assert len(annotations) == 1, f"expected 1 annotation, got {annotations}"
    assert "check_inputs_conf_disabled_default" in annotations[0]


def test_multiple_errors_one_annotation_each(tmp_path: Path) -> None:
    """BDD (d): N error findings produce N annotations, exit 1."""
    report = {
        "request_id": "multi",
        "reports": [
            {
                "groups": [
                    {
                        "name": "g1",
                        "checks": [
                            {
                                "name": f"check_error_{i}",
                                "result": "error",
                                "messages": [{"message": f"error #{i}", "result": "error"}],
                            }
                            for i in range(3)
                        ],
                    }
                ]
            }
        ],
    }
    path = tmp_path / "multi.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = run_parser(path)
    assert result.returncode == 1
    annotations = [line for line in result.stdout.splitlines() if line.startswith("::error file=")]
    assert len(annotations) == 3
    for i in range(3):
        assert any(f"check_error_{i}" in a for a in annotations)


def test_in_expect_list_suppressed() -> None:
    """BDD (e): an error finding listed in the expect file is suppressed (exit 0)."""
    result = run_parser(
        FIXTURES / "in_expect_list.json",
        "--expect-file",
        str(FIXTURES / "in_expect_list_expect.yaml"),
    )
    assert result.returncode == 0, (
        f"expected exit 0 after suppression, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "AppInspect passed" in result.stdout
    assert "1 suppressed" in result.stdout
    assert "::error file=" not in result.stdout


def test_in_expect_list_without_expect_file_fails() -> None:
    """Inverse check: same fixture WITHOUT the expect file → exit 1.

    Guards against false-negative tests where the parser passes for the wrong
    reason. Points the parser at a non-existent file so the suppression set
    is empty and the error finding is surfaced.
    """
    result = run_parser(
        FIXTURES / "in_expect_list.json",
        "--expect-file",
        str(FIXTURES / "does_not_exist.yaml"),
    )
    assert result.returncode == 1
    assert "check_for_binary_files_without_source_code" in result.stdout


def test_malformed_json_exit_one() -> None:
    """BDD (f): malformed JSON exits 1 with explanatory stderr message."""
    result = run_parser(FIXTURES / "malformed.json")
    assert result.returncode == 1
    assert "malformed AppInspect JSON" in result.stderr
    assert "::error::" in result.stderr


def test_expect_file_string_list_schema(tmp_path: Path) -> None:
    """The parser must tolerate the spec L142 string-list schema (accepted_errors)."""
    expect = tmp_path / "expect.yaml"
    expect.write_text("accepted_errors:\n  - check_xyz\n", encoding="utf-8")
    report = {
        "reports": [
            {
                "groups": [
                    {
                        "name": "g",
                        "checks": [
                            {
                                "name": "check_xyz",
                                "result": "error",
                                "messages": [{"message": "boom", "result": "error"}],
                            }
                        ],
                    }
                ]
            }
        ]
    }
    rpath = tmp_path / "report.json"
    rpath.write_text(json.dumps(report), encoding="utf-8")
    result = run_parser(rpath, "--expect-file", str(expect))
    assert result.returncode == 0
    assert "AppInspect passed" in result.stdout


def test_parser_loc_under_cap() -> None:
    """Spec L75-77: parser must be < 400 non-blank, non-comment LOC."""
    n = sum(
        1
        for raw in PARSER.read_text(encoding="utf-8").splitlines()
        if (s := raw.lstrip()) and not s.startswith("#")
    )
    assert n < 400, f"parser is {n} LOC; cap is 400"


def test_no_slop_markers_in_parser() -> None:
    """CLAUDE.md §14 grep gate: production code must not contain slop markers."""
    src = PARSER.read_text(encoding="utf-8").lower()
    for marker in ("mock", "fake", "dummy", "hardcoded", "simulated"):
        assert marker not in src, f"forbidden marker '{marker}' present in parser"


@pytest.mark.parametrize(
    "fixture",
    [
        "zero_findings.json",
        "one_error.json",
        "mixed.json",
        "in_expect_list.json",
        "empty_reports.json",
        "missing_reports.json",
    ],
)
def test_fixtures_are_valid_json(fixture: str) -> None:
    """Every committed fixture (except malformed.json) must be valid JSON."""
    json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))


# Regression tests for cicd-05 silent-failure traps caught by the
# pr-review-toolkit silent-failure-hunter on the original PR #122. Without
# these, an AppInspect run that bailed before checks (B1) or a typo'd
# expect.yaml (B2) would silently green-stamp the gate.


def test_b1_empty_reports_array_fails_loud() -> None:
    """B1: `{"reports": []}` from an AppInspect crash must NOT print 'passed'."""
    result = run_parser(FIXTURES / "empty_reports.json")
    assert result.returncode == 1
    assert "no `reports[]` envelope" in result.stderr or "empty" in result.stderr.lower()
    assert "passed" not in result.stdout.lower()


def test_b1_missing_reports_key_fails_loud() -> None:
    """B1: a body without any `reports` key (e.g., `{"success": false}`) must fail."""
    result = run_parser(FIXTURES / "missing_reports.json")
    assert result.returncode == 1
    assert "::error::" in result.stderr
    assert "passed" not in result.stdout.lower()


def test_b2_malformed_expect_yaml_clean_annotation(tmp_path: Path) -> None:
    """B2: a YAML syntax error in expect.yaml surfaces as `::error`, not a traceback."""
    expect = tmp_path / "expect.yaml"
    expect.write_text("accepted_errors:\n  - check_a\n  : not_valid\n", encoding="utf-8")
    rpath = tmp_path / "report.json"
    rpath.write_text(
        json.dumps({"reports": [{"groups": [{"checks": []}]}]}),
        encoding="utf-8",
    )
    result = run_parser(rpath, "--expect-file", str(expect))
    assert result.returncode == 1
    assert "::error" in result.stderr
    assert "malformed YAML" in result.stderr
    assert "Traceback" not in result.stderr


def test_b2_scalar_accepted_errors_rejected(tmp_path: Path) -> None:
    """B2: `accepted_errors: check_xyz` (scalar, not list) must fail loud.

    Previously this fell through to the object-keyed branch and silently
    used `{"accepted_errors"}` as a phantom suppression key — letting a
    real error finding pass if its name happened to match.
    """
    expect = tmp_path / "expect.yaml"
    expect.write_text("accepted_errors: check_xyz\n", encoding="utf-8")
    rpath = tmp_path / "report.json"
    rpath.write_text(
        json.dumps({"reports": [{"groups": [{"checks": []}]}]}),
        encoding="utf-8",
    )
    result = run_parser(rpath, "--expect-file", str(expect))
    assert result.returncode == 1
    assert "::error" in result.stderr
    assert "accepted_errors" in result.stderr
    assert "list" in result.stderr

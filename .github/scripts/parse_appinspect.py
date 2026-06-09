#!/usr/bin/env python3
"""Splunk AppInspect report parser — error-severity gate.

Reads an AppInspect JSON report, walks `reports[].groups[].checks[]`, counts
entries with `result == "error"` (case-insensitive), and emits one GitHub
Actions annotation per finding via stdout. Exits 0 when no errors remain,
1 otherwise.

Findings whose check `name` matches an entry in the expect file (default:
`splunk_apps/splunkgate_app/.appinspect.expect.yaml`) are suppressed.
Verbatim string match on `name`. The expect-file schema tolerates both
forms (story-cicd-05 spec L142):

  1. Top-level `accepted_errors:` list of `check_name` strings.
  2. Top-level dict whose KEYS are `check_name`s (the schema currently in use
     in `splunk_apps/splunkgate_app/.appinspect.expect.yaml`, mirrored from
     the CIMplicity AI 2025 winner). An empty `{}` body means zero suppressions.

Used by:
- `.github/workflows/ci.yml` `appinspect` job (post-`splunk-appinspect inspect`).
- The shell verification block in `docs/stories/story-cicd-05-appinspect-gate.md`.

CLI shape:
    python parse_appinspect.py <report.json> [--expect-file PATH]

The `--expect-file` flag lets the pytest suite point at a fixture-local
expect file without mutating the project-level one.

Schema reference (verified at runtime against splunk-appinspect 4.2.1):

    {
      "reports": [
        {
          "groups": [
            {
              "name": "<group_name>",
              "checks": [
                {
                  "name": "<check_name>",
                  "result": "error" | "failure" | "warning" | "manual_check"
                           | "success" | "skipped" | "not_applicable",
                  "messages": [
                    {"message": "<human-readable>", "result": "<same as check>"}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }

Spec drift note: story-cicd-05 spec L141 documents the top level as
`groups[].checks[]`. The real tool wraps groups inside `reports[]`, so this
parser walks `reports[].groups[].checks[]`. Check field is `name`, not
`check_name`. Documented for future maintainers; do not "fix" the walk.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EXPECT_FILE = Path("splunk_apps/splunkgate_app/.appinspect.expect.yaml")
ANNOTATION_FILE = "splunk_apps/splunkgate_app/"
ERROR_RESULT = "error"


def _coerce_entry(entry: object) -> str | None:
    """Pull a check_name out of an `accepted_errors` list entry, if possible."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        name = entry.get("check_name")
        if isinstance(name, str):
            return name
    return None


def _suppressed_from_list(entries: list[object]) -> set[str]:
    return {n for n in (_coerce_entry(e) for e in entries) if n is not None}


def _parse_loaded(data: object) -> set[str]:
    """Pull the suppression set out of a yaml-loaded body."""
    if isinstance(data, list):
        return _suppressed_from_list(data)
    if isinstance(data, dict):
        accepted = data.get("accepted_errors")
        if isinstance(accepted, list):
            return _suppressed_from_list(accepted)
        # Object-keyed-by-check-name shape (the production file's schema).
        return {k for k in data if isinstance(k, str)}
    return set()


def load_expect(expect_path: Path) -> set[str]:
    """Load the set of suppressed check names from the expect YAML.

    Tolerates three shapes:
      - file missing or empty body → empty set
      - top-level list under key `accepted_errors`: each entry is a str OR a
        dict with `check_name` key
      - top-level dict (no `accepted_errors` key) → keys ARE check names
    """
    if not expect_path.exists():
        return set()
    raw = expect_path.read_text(encoding="utf-8")
    if not raw.strip():
        return set()
    return _parse_loaded(yaml.safe_load(raw))


def iter_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Yield every check dict from `reports[].groups[].checks[]`."""
    out: list[dict[str, Any]] = []
    reports = report.get("reports", [])
    if not isinstance(reports, list):
        return out
    for r in reports:
        if not isinstance(r, dict):
            continue
        groups = r.get("groups", [])
        if not isinstance(groups, list):
            continue
        for g in groups:
            if not isinstance(g, dict):
                continue
            checks = g.get("checks", [])
            if not isinstance(checks, list):
                continue
            out.extend(c for c in checks if isinstance(c, dict))
    return out


def first_message(check: dict[str, Any]) -> str:
    """Return the first human-readable message text for a finding."""
    messages = check.get("messages")
    if isinstance(messages, list) and messages:
        msg = messages[0]
        if isinstance(msg, dict):
            text = msg.get("message")
            if isinstance(text, str):
                return text.strip().splitlines()[0]
    description = check.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip().splitlines()[0]
    return "(no message)"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a Splunk AppInspect JSON report and gate on error-severity findings."
    )
    parser.add_argument("report", type=Path, help="Path to AppInspect JSON report")
    parser.add_argument(
        "--expect-file",
        type=Path,
        default=DEFAULT_EXPECT_FILE,
        help="Path to the YAML expect file listing suppressed check names "
        f"(default: {DEFAULT_EXPECT_FILE})",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        raw = args.report.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::cannot read AppInspect report {args.report}: {exc}", file=sys.stderr)
        return 1
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::malformed AppInspect JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(report, dict):
        print("::error::AppInspect report root must be a JSON object", file=sys.stderr)
        return 1

    suppressed = load_expect(args.expect_file)

    errors_emitted = 0
    suppressed_count = 0
    for check in iter_checks(report):
        result = check.get("result")
        if not isinstance(result, str) or result.lower() != ERROR_RESULT:
            continue
        name = check.get("name") or "(unknown check)"
        if name in suppressed:
            suppressed_count += 1
            continue
        message = first_message(check)
        print(f"::error file={ANNOTATION_FILE}::{name}: {message}")
        errors_emitted += 1

    if errors_emitted:
        print(
            f"AppInspect FAILED: {errors_emitted} error-severity finding(s); "
            f"{suppressed_count} suppressed via {args.expect_file}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"AppInspect passed (no error-severity findings); "
        f"{suppressed_count} suppressed via {args.expect_file}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

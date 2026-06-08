"""AppInspect JSON report post-processor.

Reads `appinspect-report.json` produced by
`splunk-appinspect inspect ... --data-format json`, walks
`reports -> groups -> checks`, separates findings by `result`, and
exits 1 if any check has `result == "error"` that is NOT listed in
the app's `.appinspect.expect.yaml` suppression file.

Result handling uses an allow-list (PASS_RESULTS) — anything not on it
blocks the build, so a future AppInspect severity like `critical` or
`fatal` is loud by default. Per
`context/05-splunk-core/09-appinspect.md`:

- `success`        passes silently
- `not_applicable` passes silently
- `skipped`        passes silently
- `warning`        passes; documented separately in `.appinspect.warnings.md`
- `manual_check`   passes; listed in `.appinspect.manualcheck.yaml`
- `error`/`failure`/anything-else BLOCKS unless suppressed in `.expect.yaml`

CLI: `python _appinspect_postprocess.py <report.json> [--expect-file PATH]`

Writes a human-readable summary to `appinspect-summary.txt` next to
the report. Exit codes:
- 0: no blocking findings (or all blocking findings are in expect.yaml)
- 1: at least one blocking finding NOT suppressed
- 2: malformed report or missing files
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import TypedDict

import yaml

# Allow-list rather than deny-list: anything NOT in this set is treated as
# blocking. Future AppInspect releases could introduce a new severity
# (`critical`, `fatal`, etc.) that a deny-list would silently let through.
# Inverting the contract makes the gate loud on unknown results.
PASS_RESULTS = {"success", "not_applicable", "skipped", "warning", "manual_check"}


class CheckEntry(TypedDict, total=False):
    name: str
    result: str
    messages: list[object]


def _walk_checks(report: dict[str, object]) -> list[CheckEntry]:
    """Flatten reports -> groups -> checks into a single list."""
    out: list[CheckEntry] = []
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
            out.extend(c for c in checks if isinstance(c, dict))  # type: ignore[misc]
    return out


def _load_suppressions(expect_path: Path) -> set[str]:
    """Return the set of check names suppressed in .appinspect.expect.yaml.

    Empty/missing file returns an empty set; never raises on the empty case
    because an empty expect file is the explicit "no suppressions" contract.
    Entries without a non-empty `comment` field are rejected with ValueError
    — Splunkbase reviewer precedent requires every suppression to carry a
    human-readable justification.
    """
    if not expect_path.exists():
        return set()
    data = yaml.safe_load(expect_path.read_text()) or {}
    if not isinstance(data, dict):
        return set()
    suppressed: set[str] = set()
    for name, value in data.items():
        if not isinstance(value, dict):
            msg = f"expect.yaml entry {name!r} is not a mapping"
            raise TypeError(msg)
        comment = value.get("comment")
        if not isinstance(comment, str) or not comment.strip():
            msg = f"expect.yaml entry {name!r} missing non-empty 'comment'"
            raise ValueError(msg)
        suppressed.add(name)
    return suppressed


def _summarize(checks: list[CheckEntry], suppressed: set[str]) -> tuple[str, list[CheckEntry]]:
    """Return (summary table string, list of unsuppressed blocking checks)."""
    by_result: Counter[str] = Counter(c.get("result", "?") for c in checks)
    blocking_unsuppressed = [
        c for c in checks if c.get("result") not in PASS_RESULTS and c.get("name") not in suppressed
    ]
    lines = ["AppInspect summary", "==================="]
    for result, count in sorted(by_result.items()):
        lines.append(f"  {result:<16} {count}")
    lines.append("")
    if blocking_unsuppressed:
        lines.append("Unsuppressed blocking findings:")
        lines.extend(f"  - {c.get('name', '?')}: {c.get('result')}" for c in blocking_unsuppressed)
    else:
        lines.append("No unsuppressed blocking findings.")
    return "\n".join(lines) + "\n", blocking_unsuppressed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to appinspect-report.json")
    parser.add_argument(
        "--expect-file",
        type=Path,
        default=Path("splunk_apps/splunkgate_app/.appinspect.expect.yaml"),
        help="Path to .appinspect.expect.yaml suppressions",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Optional summary output path; defaults to <report-dir>/appinspect-summary.txt",
    )
    args = parser.parse_args(argv)

    if not args.report.exists():
        sys.stderr.write(f"report not found: {args.report}\n")
        return 2

    try:
        report = json.loads(args.report.read_text())
    except json.JSONDecodeError as e:
        sys.stderr.write(f"malformed JSON in {args.report}: {e}\n")
        return 2

    checks = _walk_checks(report)
    try:
        suppressed = _load_suppressions(args.expect_file)
    except (TypeError, ValueError) as e:
        sys.stderr.write(f"invalid .appinspect.expect.yaml: {e}\n")
        return 2
    summary, blocking = _summarize(checks, suppressed)

    summary_file = args.summary_file or (args.report.parent / "appinspect-summary.txt")
    summary_file.write_text(summary)
    sys.stdout.write(summary)

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())

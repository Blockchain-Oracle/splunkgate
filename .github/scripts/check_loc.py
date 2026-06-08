#!/usr/bin/env python3
"""400-LOC cap enforcement.

Walks `*.py` files (defaults: packages/, eval/, splunk_apps/splunkgate_app/bin/),
counts non-blank non-pure-comment lines per file, and rejects any file
exceeding the threshold. Used by both the `loc-cap` CI job (story-cicd-03)
and the pre-commit hook (story-cicd-04).

A line counts as LOC when, after `lstrip()`, it is non-empty AND does not
start with `#`. Module docstrings DO count as LOC (intentional per spec).

There is no `# noqa: loc-cap` escape hatch. Split via composition or extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path

THRESHOLD = 400

DEFAULT_ROOTS = ("packages", "eval", "splunk_apps/splunkgate_app/bin")
SKIP_DIR_NAMES = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def count_loc(path: Path) -> int:
    """Count non-blank non-pure-comment lines in a Python source file."""
    n = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            stripped = raw.lstrip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            n += 1
    return n


def iter_py_files(roots: list[Path]) -> list[Path]:
    """Yield Python source files under the given roots, skipping cache dirs."""
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            out.append(path)
    return sorted(out)


def main(argv: list[str]) -> int:
    if argv:
        targets = [Path(p) for p in argv]
        # When argv-driven (pre-commit hook), allow non-existent paths to be skipped
        # silently rather than erroring — pre-commit passes only changed files.
        files = [p for p in targets if p.is_file() and p.suffix == ".py"]
    else:
        roots = [Path(r) for r in DEFAULT_ROOTS]
        files = iter_py_files(roots)

    violations = 0
    for f in files:
        loc = count_loc(f)
        if loc > THRESHOLD:
            print(
                f"::error file={f}::File has {loc} LOC (cap: {THRESHOLD}). "
                f"Split it via composition or extraction.",
                file=sys.stderr,
            )
            violations += 1

    if violations:
        print(
            f"::error::{violations} file(s) exceed {THRESHOLD} LOC. See above for details.",
            file=sys.stderr,
        )
        return 1
    print(f"All files within {THRESHOLD} LOC cap.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

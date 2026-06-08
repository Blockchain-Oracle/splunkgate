"""Deterministic tarball packer for the SplunkGate Splunk app.

Story-app-12 contract is "second build produces the same sha256." On
macOS the system `tar` is BSD libarchive which lacks GNU's `--mtime`,
`--sort=name`, `--numeric-owner` flags — so we cannot rely on the
shell `tar` binary for determinism across developer + CI environments
(macOS dev box vs Ubuntu CI runner). Python's stdlib `tarfile` is the
portable answer: same bytes on every OS at the same Python version,
which uv-lock already pins for both lanes.

The packer:
- walks the input directory in sorted order (TarInfo.name comparison)
- zeroes mtime, uid/gid/uname/gname
- skips a small inline allowlist of dev cruft
- writes a gzip tarball with mtime=0 (gzip header includes its own
  timestamp by default which would break determinism)

Usage:
    python scripts/_pack_tarball.py \\
        --source splunk_apps/splunkgate_app \\
        --top-level splunkgate_app \\
        --output dist/splunkgate_app-1.0.0.tgz
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import io
import sys
import tarfile
from pathlib import Path

# Dev cruft + operations-tooling patterns that must NEVER appear in a
# release tarball. Matched against POSIX-style relative paths (relative
# to source dir). `scripts/` and `tests/` live inside the app source
# tree for repo-local CI convenience but are NOT runtime artifacts —
# stripping them keeps Splunkbase AppInspect from flagging bash/JSON
# fixtures + keeps the artifact minimal (~40 KB vs ~55 KB).
DEV_CRUFT_PATTERNS = (
    "__pycache__",
    "__pycache__/*",
    "*/__pycache__",
    "*/__pycache__/*",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*/.DS_Store",
    "tests",
    "tests/*",
    "*/tests",
    "*/tests/*",
    "scripts",
    "scripts/*",
    "*/scripts",
    "*/scripts/*",
    ".pytest_cache",
    ".pytest_cache/*",
    "*/.pytest_cache",
    "*/.pytest_cache/*",
    "appinspect-report.json",
    "appinspect-summary.txt",
    ".appinspect.expect.yaml.bak",
    ".mypy_cache",
    ".mypy_cache/*",
    "*/.mypy_cache",
    "*/.mypy_cache/*",
)


def _is_cruft(rel_path: str) -> bool:
    """Return True if `rel_path` matches any dev-cruft pattern."""
    return any(fnmatch.fnmatch(rel_path, pat) for pat in DEV_CRUFT_PATTERNS)


def _normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip nondeterministic fields from a TarInfo entry."""
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    # Splunk requires regular files to be 0644 and dirs to be 0755; normalize
    # any group/world write bits to keep AppInspect happy on the executable
    # checks.
    if info.isdir():
        info.mode = 0o755
    elif info.mode & 0o111:
        # Preserve executable bit on shell scripts but mask off write bits.
        info.mode = 0o755
    else:
        info.mode = 0o644
    return info


def _gather(source: Path) -> list[Path]:
    """Return sorted list of paths under `source`, excluding cruft."""
    paths: list[Path] = []
    for p in source.rglob("*"):
        rel = p.relative_to(source).as_posix()
        if _is_cruft(rel):
            continue
        paths.append(p)
    paths.sort(key=lambda p: p.relative_to(source).as_posix())
    return paths


def build_tarball(source: Path, top_level: str, output: Path) -> None:
    """Pack `source` into `output` as a gzipped tarball with `top_level` prefix."""
    output.parent.mkdir(parents=True, exist_ok=True)
    # gzip header carries its own mtime which would break sha256 determinism;
    # write to an in-memory buffer with mtime=0 and a fixed compresslevel.
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        # Add the top-level directory entry explicitly so the archive starts
        # with `splunkgate_app/` rather than the first file inside it.
        top_info = tarfile.TarInfo(name=top_level)
        top_info.type = tarfile.DIRTYPE
        _normalize(top_info)
        tar.addfile(top_info)
        for path in _gather(source):
            rel = path.relative_to(source).as_posix()
            arcname = f"{top_level}/{rel}"
            info = tar.gettarinfo(str(path), arcname=arcname)
            if info is None:
                continue
            _normalize(info)
            if info.isfile():
                with path.open("rb") as fh:
                    tar.addfile(info, fh)
            else:
                tar.addfile(info)
    raw = tar_buf.getvalue()
    with (
        output.open("wb") as fh,
        gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=6) as gz,
    ):
        gz.write(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--top-level", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.source.is_dir():
        sys.stderr.write(f"source not a directory: {args.source}\n")
        return 2
    build_tarball(args.source, args.top_level, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

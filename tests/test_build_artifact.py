"""Behavioral tests for the Splunkbase build artifact pipeline.

Covers the build_splunk_app_tgz.sh + _pack_tarball.py + manifest.json
contract end-to-end. Tests run the actual build script against a
temporary DIST_DIR; no mocks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_SRC = REPO_ROOT / "splunk_apps" / "splunkgate_app"
APP_CONF = APP_SRC / "default" / "app.conf"
MANIFEST = APP_SRC / "META-INF" / "manifest.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_splunk_app_tgz.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_splunkbase_artifact.sh"
PACK_HELPER = REPO_ROOT / "scripts" / "_pack_tarball.py"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _app_version() -> str:
    for line in APP_CONF.read_text().splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip()
    msg = "version line not found in app.conf"
    raise AssertionError(msg)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def built_artifact(tmp_path: Path) -> Path:
    """Run the build script into a tmp DIST_DIR and return the produced tarball."""
    dist = tmp_path / "dist"
    env = {**os.environ, "DIST_DIR": str(dist), "SKIP_APPINSPECT": "1"}
    subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        check=True,
        env=env,
        capture_output=True,
    )
    artifacts = list(dist.glob("splunkgate_app-*.tgz"))
    assert len(artifacts) == 1, f"expected 1 tarball, got {artifacts}"
    return artifacts[0]


def test_manifest_exists() -> None:
    assert MANIFEST.exists()


def test_manifest_parses_and_has_expected_id() -> None:
    data = json.loads(MANIFEST.read_text())
    assert data["info"]["id"] == "splunkgate_app"


def test_manifest_version_matches_app_conf() -> None:
    data = json.loads(MANIFEST.read_text())
    assert data["info"]["version"] == _app_version()


def test_manifest_version_is_semver() -> None:
    data = json.loads(MANIFEST.read_text())
    assert SEMVER.match(data["info"]["version"])


def test_license_exists_and_is_apache_2() -> None:
    license_file = APP_SRC / "LICENSE"
    assert license_file.exists()
    head = license_file.read_text().splitlines()[:5]
    joined = "\n".join(head)
    assert "Apache License" in joined
    assert "Version 2.0" in joined


def test_build_produces_single_tarball(built_artifact: Path) -> None:
    assert built_artifact.exists()
    assert built_artifact.name == f"splunkgate_app-{_app_version()}.tgz"


def test_build_tarball_has_splunkgate_app_top_level(built_artifact: Path) -> None:
    with tarfile.open(built_artifact, "r:gz") as tar:
        names = tar.getnames()
    assert any(n == "splunkgate_app" or n.startswith("splunkgate_app/") for n in names)
    assert not any(n.startswith("splunk_apps/") for n in names)


def test_build_tarball_contains_required_files(built_artifact: Path) -> None:
    with tarfile.open(built_artifact, "r:gz") as tar:
        names = set(tar.getnames())
    required = {
        "splunkgate_app/default/app.conf",
        "splunkgate_app/README",
        "splunkgate_app/LICENSE",
        "splunkgate_app/RELEASE_NOTES.md",
        "splunkgate_app/META-INF/manifest.json",
    }
    missing = required - names
    assert not missing, f"missing in tarball: {missing}"


def test_build_tarball_omits_dev_cruft(built_artifact: Path) -> None:
    """Dev tooling (scripts/, tests/) + cache dirs must NOT ship.

    silent-failure-hunter on PR #106 caught that packaging operations
    tooling (run_appinspect.sh, _appinspect_postprocess.py, fixtures)
    inside the tarball is a Splunkbase reviewer red flag AND creates a
    circular dependency in the verify script.
    """
    with tarfile.open(built_artifact, "r:gz") as tar:
        names = tar.getnames()
    forbidden_patterns = (
        "__pycache__",
        ".pyc",
        ".DS_Store",
        "/tests/",
        "/tests",
        "/scripts/",
        "/scripts",
    )
    bad = [n for n in names if any(p in n for p in forbidden_patterns)]
    assert not bad, f"dev cruft / ops tooling in tarball: {bad}"


def test_release_notes_exists_at_app_root() -> None:
    """Splunkbase manifest declares releaseNotes.name = 'RELEASE_NOTES.md'.

    silent-failure-hunter on PR #106: missing file would surface as a
    Splunkbase listing warning at submission time.
    """
    release_notes = APP_SRC / "RELEASE_NOTES.md"
    assert release_notes.exists()
    text = release_notes.read_text()
    assert "1.0.0" in text, "RELEASE_NOTES.md should reference 1.0.0"


def test_build_script_loud_fails_when_appinspect_missing_and_not_skipped(tmp_path: Path) -> None:
    """SKIP_APPINSPECT=1 is the only acceptable way to bypass; silent skip is forbidden.

    silent-failure-hunter on PR #106 caught the silent-skip fallback. The
    fixup makes the absent-runner case exit 2 with a clear message.
    """
    # Shadow the runner so the build script sees it as missing.
    fake_app = tmp_path / "splunk_apps" / "splunkgate_app"
    fake_app.mkdir(parents=True)
    (fake_app / "default").mkdir()
    (fake_app / "default" / "app.conf").write_text("[install]\nversion = 1.0.0\n")
    # Run the build script with APP_SRC pointed at the fake tree, no runner.
    # Use SKIP_APPINSPECT=0 explicitly to exercise the loud path.
    env = {
        **os.environ,
        "DIST_DIR": str(tmp_path / "dist"),
        "REPO_ROOT": str(tmp_path),
        "SKIP_APPINSPECT": "0",
    }
    result = subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        check=False,
        env=env,
        capture_output=True,
    )
    # Exit code 2 = explicit "loud fail on missing tooling"
    assert result.returncode == 2, (
        f"expected exit 2 on missing AppInspect runner without bypass, "
        f"got {result.returncode}: stderr={result.stderr!r}"
    )


def test_build_is_deterministic(tmp_path: Path) -> None:
    """Two builds on the same source tree produce byte-identical archives."""
    dist_a = tmp_path / "dist_a"
    dist_b = tmp_path / "dist_b"
    env_a = {**os.environ, "DIST_DIR": str(dist_a), "SKIP_APPINSPECT": "1"}
    env_b = {**os.environ, "DIST_DIR": str(dist_b), "SKIP_APPINSPECT": "1"}
    subprocess.run(["bash", str(BUILD_SCRIPT)], check=True, env=env_a, capture_output=True)
    subprocess.run(["bash", str(BUILD_SCRIPT)], check=True, env=env_b, capture_output=True)
    a = next(dist_a.glob("splunkgate_app-*.tgz"))
    b = next(dist_b.glob("splunkgate_app-*.tgz"))
    assert _sha256(a) == _sha256(b), "non-deterministic build"


def test_pack_helper_normalizes_mtimes(built_artifact: Path) -> None:
    """Every TarInfo entry has mtime=0 — load-bearing for determinism."""
    with tarfile.open(built_artifact, "r:gz") as tar:
        for info in tar.getmembers():
            assert info.mtime == 0, f"{info.name}: mtime {info.mtime} != 0"


def test_pack_helper_strips_uid_gid(built_artifact: Path) -> None:
    """uid/gid/uname/gname are zeroed for cross-machine reproducibility."""
    with tarfile.open(built_artifact, "r:gz") as tar:
        for info in tar.getmembers():
            assert info.uid == 0
            assert info.gid == 0
            assert info.uname == ""
            assert info.gname == ""


def test_verify_script_succeeds_on_built_artifact(built_artifact: Path) -> None:
    rc = subprocess.run(
        ["bash", str(VERIFY_SCRIPT), str(built_artifact)],
        check=False,
        capture_output=True,
    ).returncode
    assert rc == 0


def test_verify_script_fails_on_bogus_artifact(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.tgz"
    bogus.write_text("not a real gzip file")
    rc = subprocess.run(
        ["bash", str(VERIFY_SCRIPT), str(bogus)],
        check=False,
        capture_output=True,
    ).returncode
    assert rc != 0


def test_checklist_doc_mentions_all_required_items() -> None:
    """BDD spec greps for these specific strings in the checklist doc."""
    checklist = (REPO_ROOT / "docs" / "splunkbase-submission-checklist.md").read_text()
    for needle in (
        "AppInspect",
        "Apache-2.0",
        "manifest.json",
        "README",
        "appIcon",
        "demo video",
        "eval results",
    ):
        assert needle in checklist, f"checklist missing '{needle}'"


def test_pack_helper_runs_standalone(tmp_path: Path) -> None:
    """The Python helper should be invocable directly for ad-hoc packing."""
    out = tmp_path / "out.tgz"
    rc = subprocess.run(
        [
            sys.executable,
            str(PACK_HELPER),
            "--source",
            str(APP_SRC),
            "--top-level",
            "splunkgate_app",
            "--output",
            str(out),
        ],
        check=False,
        capture_output=True,
    ).returncode
    assert rc == 0
    assert out.exists()
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "splunkgate_app/default/app.conf" in names

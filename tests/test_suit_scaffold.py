"""Structural tests for the SUIT scaffold (story-suit-scaffold)."""

from __future__ import annotations

import re
import tarfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_ROOT = _REPO_ROOT / "splunk_apps" / "splunkgate_app"
_SUIT_STATIC = _APP_ROOT / "static" / "splunkgate-suit"
_SUIT_SRC = _APP_ROOT / "src"
_DOSSIER_SOURCE = _REPO_ROOT / "web" / "styles" / "designer" / "splunkgate-base.css"


def test_built_bundle_committed() -> None:
    """The Dossier tokens bundle ships in static/ for all SUIT views to reference."""
    assert (_SUIT_STATIC / "tokens.css").exists()


def test_dev_source_present() -> None:
    """The webpack/TypeScript scaffold lives under src/ for the SUIT dashboards."""
    assert (_SUIT_SRC / "package.json").exists()
    assert (_SUIT_SRC / "webpack.config.js").exists()
    assert (_SUIT_SRC / "tsconfig.json").exists()


def test_scaffold_placeholder_removed_in_pr18() -> None:
    """The PR-15 scaffold placeholder (_suit_hello.xml, hello.js, hello.tsx, default.meta stanza)
    is deleted in PR #18 alongside the verdict_inspector rebuild."""
    view = _APP_ROOT / "default" / "data" / "ui" / "views" / "_suit_hello.xml"
    assert not view.exists(), "_suit_hello.xml must be removed in PR #18"
    assert not (_SUIT_STATIC / "hello.js").exists(), "hello.js bundle must be removed in PR #18"
    assert not (_SUIT_SRC / "views" / "hello.tsx").exists(), (
        "hello.tsx source must be removed in PR #18"
    )
    meta = (_APP_ROOT / "metadata" / "default.meta").read_text(encoding="utf-8")
    assert "[views/_suit_hello]" not in meta, "default.meta stanza for _suit_hello must be removed"


def test_brand_kit_tokens_ported() -> None:
    """The Dossier palette (`#F1ECE1` paper, `#BC3A26` vermillion accent) is in the bundle CSS."""
    css = (_SUIT_STATIC / "tokens.css").read_text(encoding="utf-8")
    assert "#F1ECE1" in css  # --paper
    assert "#BC3A26" in css  # --accent
    assert "Newsreader" in css
    assert "Hanken Grotesk" in css
    assert "JetBrains Mono" in css


def test_dossier_tokens_match_source_of_truth() -> None:
    """Built SUIT tokens.css carries the same Dossier hex values the landing page uses."""
    if not _DOSSIER_SOURCE.exists():
        # The Dossier CSS lives in the web/ tree; if web/ is removed in a
        # future restructure, this guard goes away — but until then the SUIT
        # bundle must not drift from the landing page's source of truth.
        return
    source = _DOSSIER_SOURCE.read_text(encoding="utf-8")
    built = (_SUIT_STATIC / "tokens.css").read_text(encoding="utf-8")
    for token in ("#F1ECE1", "#BC3A26"):
        assert token in source, f"{token} missing from Dossier source — restate the SUIT spec"
        assert token in built, f"{token} present in Dossier but missing from SUIT bundle (drift)"


def test_dev_and_built_tokens_match() -> None:
    """src/styles/tokens.css (dev) and static/.../tokens.css (built) declare the same Dossier tokens."""
    pattern = re.compile(r"--[\w-]+:\s*[^;]+;")
    dev = {
        m.group(0).strip()
        for m in pattern.finditer((_SUIT_SRC / "styles" / "tokens.css").read_text(encoding="utf-8"))
    }
    built = {
        m.group(0).strip()
        for m in pattern.finditer((_SUIT_STATIC / "tokens.css").read_text(encoding="utf-8"))
    }
    # The committed bundle must declare AT LEAST every token the dev tree declares.
    # (The bundle can omit dev-only ergonomic helpers like body element selectors.)
    missing = dev - built
    assert not missing, (
        f"Dossier tokens declared in dev tree but missing from built bundle: {missing}"
    )


def test_tarball_excludes_src_includes_static() -> None:
    """`_pack_tarball.py` cruft filter keeps src/ out and static/splunkgate-suit/ in."""
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    dist = _REPO_ROOT / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "SKIP_APPINSPECT": "1"}
    try:
        subprocess.run(
            ["bash", str(_REPO_ROOT / "scripts" / "build_splunk_app_tgz.sh")],
            check=True,
            env=env,
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = (
            f"build_splunk_app_tgz.sh failed (rc={exc.returncode})\n"
            f"--- stdout ---\n{exc.stdout}\n"
            f"--- stderr ---\n{exc.stderr}"
        )
        raise AssertionError(msg) from exc
    tgz = next(dist.glob("splunkgate_app-*.tgz"))
    with tarfile.open(tgz, "r:gz") as tar:
        names = tar.getnames()

    # Negative control: no developer-source-tree paths leak.
    top = "splunkgate_app"
    src_leaks = [n for n in names if n == f"{top}/src" or n.startswith(f"{top}/src/")]
    assert src_leaks == [], f"src/ leaked into tarball: {src_leaks}"

    node_modules_leaks = [n for n in names if "/node_modules/" in n or n.endswith("/node_modules")]
    assert node_modules_leaks == [], f"node_modules leaked: {node_modules_leaks}"

    lockfile_leaks = [
        n for n in names if n.endswith(("/package-lock.json", "/pnpm-lock.yaml", "/yarn.lock"))
    ]
    assert lockfile_leaks == [], f"lockfile leaked: {lockfile_leaks}"

    appinspect_dirt = [
        n for n in names if n.endswith((".appinspect.warnings.md", ".appinspect.manualcheck.yaml"))
    ]
    assert appinspect_dirt == [], f"appinspect dirt in tarball: {appinspect_dirt}"

    # Positive control: the three SUIT dashboards + Dossier tokens do ship.
    # The PR-15 hello.js placeholder is removed in PR #18 — see
    # test_scaffold_placeholder_removed_in_pr18 above for the negative
    # check on that artefact.
    suit_entries = [n for n in names if "splunkgate-suit/" in n]
    assert any(n.endswith("tokens.css") for n in suit_entries)
    assert any(n.endswith("evidence_pack.js") for n in suit_entries)
    assert any(n.endswith("agent_risk_overview.js") for n in suit_entries)
    assert any(n.endswith("verdict_inspector.js") for n in suit_entries)

    # Tripwire: silent over-exclusion (a future glob that eats too much) will
    # drop the entry count below the current baseline.
    assert len(names) >= 30, f"tarball entry count regressed: {len(names)}"

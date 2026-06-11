"""Structural tests for `.github/workflows/release.yml` (story-cicd-08)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


def _load() -> dict[str, Any]:
    """Parse the YAML once per test."""
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_workflow_yaml_parses() -> None:
    """Release workflow must parse as valid YAML."""
    parsed = _load()
    assert "jobs" in parsed
    assert "build-and-sign" in parsed["jobs"]
    assert "gh-release" in parsed["jobs"]


def test_tag_trigger_glob_is_v_semver() -> None:
    """Tag-trigger glob is `v*.*.*` so only versioned tags fire the pipeline."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    # PyYAML normalises [...] vs flow vs block; assert via substring to keep the
    # test robust to formatting.
    assert "tags:" in text
    assert "v*.*.*" in text


def test_id_token_write_permission_present() -> None:
    """sigstore OIDC requires `id-token: write` on the signing job."""
    parsed = _load()
    perms = parsed["jobs"]["build-and-sign"]["permissions"]
    assert perms["id-token"] == "write"
    assert perms["contents"] == "write"


def test_sigstore_action_is_used() -> None:
    """`sigstore/gh-action-sigstore-python` step must be present in build-and-sign."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "sigstore/gh-action-sigstore-python" in text


def test_gh_release_action_with_auto_release_notes() -> None:
    """gh-release uses softprops/action-gh-release v2 with generate_release_notes: true."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "softprops/action-gh-release@v2" in text
    assert "generate_release_notes: true" in text


def test_prerelease_predicate_includes_rc_and_alpha() -> None:
    """Pre-release flag fires on tags containing `rc` OR `alpha`."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "'rc'" in text
    assert "'alpha'" in text

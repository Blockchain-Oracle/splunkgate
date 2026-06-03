"""Meta-test: bandit catches MEDIUM+ findings on a known violator.

Story-cicd-07 BDD asserts both:
  (a) bandit on aegis_judges placeholder code exits 0
  (b) bandit on a deliberately-crafted violator exits non-zero
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_bandit(target: Path, config: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["uv", "run", "--with", "bandit", "bandit", "-r", str(target)]
    if config is not None:
        cmd += ["-c", str(config)]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_bandit_clean_on_aegis_judges_placeholder() -> None:
    """bandit -r packages/aegis_judges/src/ exits 0 on current placeholder code."""
    target = REPO_ROOT / "packages" / "aegis_judges" / "src"
    config = REPO_ROOT / ".bandit"
    result = _run_bandit(target, config)
    assert result.returncode == 0, (
        f"bandit failed on placeholder code:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_bandit_fires_on_eval_violator(tmp_path: Path) -> None:
    """bandit catches `eval(user_input)` (rule B307) in a tmp file."""
    violator = tmp_path / "violator.py"
    violator.write_text("def run(user_input: str) -> object:\n    return eval(user_input)\n")
    result = _run_bandit(tmp_path)
    assert result.returncode != 0, (
        f"bandit DID NOT catch eval() violator:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "B307" in result.stdout or "eval" in result.stdout.lower(), (
        f"bandit output didn't mention eval/B307:\n{result.stdout}"
    )

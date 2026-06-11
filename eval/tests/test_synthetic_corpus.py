"""Behavioural tests for the synthetic corpus generator + loaders (story-eval-01)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from splunkgate_eval import (
    EvalPrompt,
    load_benign_control,
    load_multi_turn_injection,
    load_tool_call_abuse,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _REPO_ROOT / "Synthetic-Data" / "generate_agent_verdicts.py"
_CORPUS_DIR = _REPO_ROOT / "Synthetic-Data" / "jailbreak_corpus"
_FILES = {
    "tool_call_abuse": _CORPUS_DIR / "tool_call_abuse.jsonl",
    "multi_turn_injection": _CORPUS_DIR / "multi_turn_injection.jsonl",
    "benign_control": _CORPUS_DIR / "benign_control.jsonl",
}
_MIN_COUNTS = {
    "tool_call_abuse": 200,
    "multi_turn_injection": 150,
    "benign_control": 300,
}
_TURN_SEPARATORS = ("\n\nHuman:", "\n\nUser:")


@pytest.fixture(scope="module", autouse=True)
def _ensure_corpus_present() -> None:
    """Run the generator once before the test module if outputs are missing."""
    if all(p.exists() for p in _FILES.values()):
        return
    result = subprocess.run(
        [sys.executable, str(_GENERATOR)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"generator exit={result.returncode}\n{result.stderr}"


def test_generator_runs_to_completion_under_60s() -> None:
    """The generator script exits 0 within the 60-second budget."""
    result = subprocess.run(
        [sys.executable, str(_GENERATOR)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "[5/5]" in result.stdout, "expected the 5/5 DNS-Guard-style summary header"


@pytest.mark.parametrize("name", sorted(_FILES))
def test_corpus_file_exists(name: str) -> None:
    """Each of the three JSONL files exists on disk."""
    assert _FILES[name].exists(), f"{_FILES[name]} missing"


@pytest.mark.parametrize("name", sorted(_FILES))
def test_corpus_meets_minimum_line_count(name: str) -> None:
    """Each JSONL has at least the spec-required record count."""
    lines = [line for line in _FILES[name].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= _MIN_COUNTS[name], (
        f"{name}: expected ≥ {_MIN_COUNTS[name]} records, found {len(lines)}"
    )


def test_every_record_validates_as_eval_prompt() -> None:
    """Every JSONL line parses as a valid EvalPrompt."""
    for path in _FILES.values():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            EvalPrompt.model_validate_json(line)


def test_multi_turn_records_have_at_least_four_turn_separators() -> None:
    """Every multi-turn record must contain ≥ 4 turn separators per the MSJ schema."""
    for line in _FILES["multi_turn_injection"].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        separator_count = sum(rec["prompt"].count(sep) for sep in _TURN_SEPARATORS)
        assert separator_count >= 4, f"only {separator_count} separators in {rec['id']}"


def test_benign_records_all_have_allow_verdict() -> None:
    """Every benign-control record expects ALLOW."""
    for line in _FILES["benign_control"].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        assert rec["expected_verdict"] == "ALLOW"


def test_source_citation_is_non_empty_on_every_record() -> None:
    """source_citation is load-bearing for provenance audit — empty is a smell."""
    for path in _FILES.values():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            assert rec["source_citation"].strip(), f"empty source_citation in {rec['id']}"


def test_generator_is_deterministic_under_same_seed() -> None:
    """Two consecutive runs produce byte-identical JSONL files (sha256 match)."""

    def _hashes() -> dict[str, str]:
        return {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in _FILES.items()
        }

    subprocess.run([sys.executable, str(_GENERATOR)], check=True, capture_output=True, timeout=60)
    first = _hashes()
    subprocess.run([sys.executable, str(_GENERATOR)], check=True, capture_output=True, timeout=60)
    second = _hashes()
    assert first == second, "generator is non-deterministic"


def test_loaders_return_validated_pydantic_records() -> None:
    """Each public loader returns a non-empty list of EvalPrompt instances."""
    for loader in (load_tool_call_abuse, load_multi_turn_injection, load_benign_control):
        records = loader()
        assert records, f"{loader.__name__} returned empty list"
        assert all(isinstance(r, EvalPrompt) for r in records)


def test_loader_counts_match_underlying_jsonl_line_counts() -> None:
    """Each loader's len() equals the non-blank line count of its source file."""
    pairs = (
        (load_tool_call_abuse, _FILES["tool_call_abuse"]),
        (load_multi_turn_injection, _FILES["multi_turn_injection"]),
        (load_benign_control, _FILES["benign_control"]),
    )
    for loader, path in pairs:
        line_count = sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        assert len(loader()) == line_count


def test_eval_prompt_rejects_unknown_category() -> None:
    """Literal Pydantic field rejects unknown categories at parse time."""
    payload = {
        "id": "00000000-0000-0000-0000-000000000000",
        "category": "spaghetti",
        "prompt": "hi",
        "expected_verdict": "ALLOW",
        "expected_severity": "NONE_SEVERITY",
        "source_citation": "test",
    }
    with pytest.raises(ValidationError):
        EvalPrompt.model_validate(payload)


def test_synthetic_data_folder_uses_corrected_spelling() -> None:
    """ADR-011 — folder is `Synthetic-Data/` (corrected); DNS Guard's typo NOT mirrored."""
    assert (_REPO_ROOT / "Synthetic-Data").is_dir()
    assert not (_REPO_ROOT / "Syntethic-Data").exists()

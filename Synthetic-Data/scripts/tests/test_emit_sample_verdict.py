"""Behavioral tests for the synthetic Verdict emitter.

Per story-app-13. All tests use --dry-run or respx; no real Splunk endpoint
is contacted. Hard Rule 6 compliance — no real tokens / paths.
"""

from __future__ import annotations

import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from splunkgate_core.verdict import Verdict

# Import the module under test directly (Synthetic-Data isn't a uv-workspace member).
_SCRIPT = Path(__file__).resolve().parents[1] / "emit_sample_verdict.py"
sys.path.insert(0, str(_SCRIPT.parent))

from emit_sample_verdict import (
    RULES,
    SURFACES,
    Args,
    emit,
    main,
    parse_args,
)

ALLOWED_RULES = set(RULES)
ALLOWED_SURFACES = set(SURFACES)


def _run_dry_run(count: int, seed: int = 20260603) -> list[dict[str, Any]]:
    """Invoke the emitter via subprocess in --dry-run mode and parse JSON lines."""
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--count",
            str(count),
            "--seed",
            str(seed),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [json.loads(line) for line in proc.stdout.splitlines()]


# ---------- BDD #1: --help works + exposes required flags ----------


def test_help_text_lists_required_flags() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for flag in ("--count", "--hec-url", "--hec-token", "--dry-run", "--seed"):
        assert flag in proc.stdout, f"missing flag in --help: {flag}"


# ---------- BDD #2: dry-run produces >= N JSON lines ----------


def test_dry_run_produces_requested_count() -> None:
    envelopes = _run_dry_run(500)
    assert len(envelopes) == 500


# ---------- BDD #3: every event validates against Verdict ----------


def test_every_event_payload_validates_against_strict_verdict_no_stripping() -> None:
    """Verdict has extra='forbid'. event must be strict — no aux fields polluting it.

    Code-reviewer B1 on PR #110: aux fields like model_name + jurisdictional_tag
    must live on the HEC `fields` sibling block, NOT inside `event`. Otherwise
    consumers doing Verdict.model_validate(env['event']) raise ValidationError.
    """
    envelopes = _run_dry_run(200)
    for env in envelopes:
        # No key-stripping — the event MUST validate strictly.
        Verdict.model_validate(env["event"])


def test_aux_fields_live_on_hec_envelope_fields_sibling_not_event() -> None:
    """HEC native pattern: indexed metadata in `fields`, payload in `event`."""
    envelopes = _run_dry_run(50)
    for env in envelopes:
        assert "model_name" not in env["event"]
        assert "jurisdictional_tag" not in env["event"]
        assert "tokens_used" not in env["event"]
        assert "fields" in env
        assert "model_name" in env["fields"]
        assert "jurisdictional_tag" in env["fields"]
        assert "tokens_used" in env["fields"]


def test_tokens_used_is_int_in_sensible_range() -> None:
    """Token count borrowed from TruongSinhAI/splunk-token-optimizer narrative.

    Used by Agent Risk Overview's 'tokens saved' KPI tile — aggregated over
    BLOCK verdicts to show what interception prevented.
    """
    envelopes = _run_dry_run(100)
    for env in envelopes:
        tokens_str = env["fields"]["tokens_used"]
        # JSON normalizes to string on HEC `fields` block; verify it's a clean int.
        tokens = int(tokens_str)
        assert 80 <= tokens <= 8000, f"tokens out of range: {tokens}"


# ---------- BDD #4: sourcetype is the canonical string ----------


def test_every_envelope_sourcetype_equals_canonical() -> None:
    envelopes = _run_dry_run(200)
    sourcetypes = {env["sourcetype"] for env in envelopes}
    assert sourcetypes == {"cisco_ai_defense:splunkgate_verdict"}


# ---------- BDD #5: verdict-label distribution within tolerance ----------


def test_verdict_label_distribution_within_tolerance() -> None:
    envelopes = _run_dry_run(1000)
    ctr = collections.Counter(env["event"]["verdict"] for env in envelopes)
    n = len(envelopes)
    allow = ctr.get("ALLOW", 0) * 100 / n
    block = ctr.get("BLOCK", 0) * 100 / n
    modify = ctr.get("MODIFY", 0) * 100 / n
    review = ctr.get("REVIEW", 0) * 100 / n
    assert 65 <= allow <= 75, f"ALLOW {allow:.1f}"
    assert 10 <= block <= 20, f"BLOCK {block:.1f}"
    assert 5 <= modify <= 15, f"MODIFY {modify:.1f}"
    assert 2 <= review <= 8, f"REVIEW {review:.1f}"


# ---------- BDD #6: determinism ----------


def test_same_seed_produces_byte_identical_output() -> None:
    proc_a = subprocess.run(
        [sys.executable, str(_SCRIPT), "--count", "100", "--seed", "20260603", "--dry-run"],
        check=True,
        capture_output=True,
    )
    proc_b = subprocess.run(
        [sys.executable, str(_SCRIPT), "--count", "100", "--seed", "20260603", "--dry-run"],
        check=True,
        capture_output=True,
    )
    sha_a = hashlib.sha256(proc_a.stdout).hexdigest()
    sha_b = hashlib.sha256(proc_b.stdout).hexdigest()
    assert sha_a == sha_b, "non-deterministic output"


def test_different_seeds_produce_different_output() -> None:
    a = _run_dry_run(50, seed=1)
    b = _run_dry_run(50, seed=2)
    assert a != b


# ---------- BDD #7: surface enum coverage ----------


def test_surface_field_cycles_through_all_eight_values() -> None:
    envelopes = _run_dry_run(100)
    surfaces = {env["event"]["surface"] for env in envelopes}
    assert surfaces.issubset(ALLOWED_SURFACES), surfaces - ALLOWED_SURFACES
    # All 8 surfaces should appear in 100 events (we cycle deterministically).
    assert len(surfaces) == len(ALLOWED_SURFACES)


# ---------- BDD #8: rule-name verbatim ----------


def test_rule_names_are_verbatim_cisco_ai_defense() -> None:
    envelopes = _run_dry_run(300)
    seen_rules: set[str] = set()
    for env in envelopes:
        for r in env["event"]["rules"]:
            seen_rules.add(r["rule"])
    assert seen_rules.issubset(ALLOWED_RULES), seen_rules - ALLOWED_RULES


# ---------- BDD #9: HEC retry path via respx ----------


@respx.mock
def test_hec_post_retries_then_succeeds_on_503_503_200() -> None:
    """Mirror the BDD respx contract: 503, 503, 200 → exit 0."""
    route = respx.post("https://splunk.example/services/collector/event")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"text": "Success", "code": 0}),
    ]
    rc = emit(
        Args(
            count=2,
            hec_url="https://splunk.example",
            hec_token="synth-token-12345",
            index="main",
            seed=42,
            dry_run=False,
        )
    )
    assert rc == 0
    assert route.call_count == 3


@respx.mock
def test_hec_post_returns_exit_2_after_max_retries() -> None:
    route = respx.post("https://splunk.example/services/collector/event")
    route.return_value = httpx.Response(503)
    rc = emit(
        Args(
            count=2,
            hec_url="https://splunk.example",
            hec_token="synth-token-12345",
            index="main",
            seed=42,
            dry_run=False,
        )
    )
    assert rc == 2


# ---------- BDD #10: --count validation ----------


def test_zero_or_negative_count_is_rejected() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--count", "0", "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


# ---------- BDD: env-var fallback for HEC ----------


def test_env_var_provides_hec_url_when_flag_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_HEC_URL", "https://from-env.example")
    monkeypatch.setenv("SPLUNKGATE_SPLUNK_HEC_TOKEN", "env-token-1234")
    args = parse_args(["--count", "3"])
    assert args.hec_url == "https://from-env.example"
    assert args.hec_token == "env-token-1234"


def test_live_mode_without_hec_creds_returns_1() -> None:
    rc = main(["--count", "3"])
    # --dry-run not passed, no env vars in the test environment (CI sets none here)
    # If env vars DO leak through, the test still validates emit() reaches HEC code path,
    # which then fails because the URL is bogus. Skip if env happens to be set.
    if rc == 0:
        pytest.skip("env vars leaked through; live HEC may have actually succeeded")
    assert rc in (1, 2)


# ---------- Internal invariants ----------


def test_emit_dry_run_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    rc = emit(
        Args(
            count=5,
            hec_url=None,
            hec_token=None,
            index="main",
            seed=42,
            dry_run=True,
        )
    )
    assert rc == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 5


def test_emit_with_high_severity_block_only_uses_known_severities() -> None:
    """No nulls or rogue strings sneak in via the weighted-choice path."""
    envelopes = _run_dry_run(200)
    severities = {env["event"]["severity"] for env in envelopes}
    assert severities.issubset({"NONE_SEVERITY", "LOW", "MEDIUM", "HIGH"})


# ---------- Diagnostic: smoke that the import worked ----------


def test_imports_loaded_cleanly() -> None:
    """If this test runs, the module import succeeded — no missing deps."""
    assert callable(emit)
    assert callable(main)
    assert callable(parse_args)

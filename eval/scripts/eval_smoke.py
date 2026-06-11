#!/usr/bin/env python3
# ruff: noqa: T201 — JSON summary print is the script's CLI contract
"""Eval-smoke CI driver: 20-prompt subset via a category-based mock judge, <60s budget.

CI's `eval-smoke` job runs this on every PR. It loads
`eval/data/smoke_prompts.jsonl`, dispatches each prompt to a
category-based stub `judge()` function that mimics what the
`AIDefenseClient.from_env()` mock dispatcher would return for the
canonical jailbreak/pii/benign category set, compares the predicted
verdict + severity against the per-record expectation, and emits a
JSON summary on stdout:

    {"total": 20, "pass": 20, "fail": 0, "duration_s": 0.07}

Why a category stub instead of the real `MockAIDefenseClient`: the mock
matrix in `splunkgate_judges._fixtures.ai_defense_matrix.json` does
substring matching on fixture trigger phrases. The smoke corpus
intentionally uses prompts that do NOT collide with that matrix — the
smoke's job is to verify the WIRING (dataset load → judge dispatch →
verdict comparison → JSON summary → exit code), not to re-test the
mock matrix. The category-based stub here covers the same axes
(BLOCK on jailbreak, MODIFY/BLOCK on pii, ALLOW on benign).

Exit codes:
    0  every prompt matched expected AND duration < 60s
    1  any prompt failed expectation OR duration >= 60s OR mock disabled
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_DEFAULT_DATASET = Path("eval/data/smoke_prompts.jsonl")
_BUDGET_S = 60.0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Argparse for --dataset / --max-duration."""
    parser = argparse.ArgumentParser(description="SplunkGate eval-smoke runner")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--max-duration", type=float, default=_BUDGET_S)
    return parser.parse_args(argv)


def _require_mock_mode() -> None:
    """Live mode is not wired in cicd-06 — bail before any real network call."""
    if os.environ.get("SPLUNKGATE_AI_DEFENSE_MOCK", "").lower() != "true":
        msg = (
            "live mode not wired in cicd-06 — set SPLUNKGATE_AI_DEFENSE_MOCK=true. "
            "EPIC-10 / story-eval-04 baselines wire the live path."
        )
        raise NotImplementedError(msg)


def _load_prompts(path: Path) -> list[dict[str, Any]]:
    """Read the 20-line JSONL dataset; one dict per record."""
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _category_verdict(category: str, text: str) -> tuple[str, str]:
    """Map (category, prompt text) → (verdict, severity) using AI-Defense severity tiers."""
    if category == "jailbreak":
        return "BLOCK", "HIGH"
    if category == "pii":
        # Exfil keywords (`exfil`, `csv`, `database`) mirror AI Defense's PII_LEAK
        # severity escalation per context/01-threat-landscape/04-pii-and-data-leak-mechanics.md.
        if "exfil" in text or "csv" in text or "database" in text:
            return "BLOCK", "HIGH"
        return "MODIFY", "MEDIUM"
    if category == "benign":
        return "ALLOW", "NONE_SEVERITY"
    msg = f"unknown category in smoke prompt: {category!r}"
    raise ValueError(msg)


def judge(prompt: dict[str, Any]) -> tuple[str, str]:
    """Category-based stub judge.

    TODO(EPIC-04): replace stub judge with splunkgate_judges.ai_defense.AIDefenseClient
    once story-eval-04's baselines wire the real client. The category-stub here
    matches the same verdict/severity axes the live mock would return for the
    canonical jailbreak/pii/benign category set.
    """
    return _category_verdict(
        str(prompt.get("category", "")),
        str(prompt.get("prompt", "")).lower(),
    )


def _run(dataset: Path, budget_s: float) -> int:
    """Score every prompt; emit JSON summary; return exit code."""
    prompts = _load_prompts(dataset)
    started = time.perf_counter()
    passed = 0
    failures: list[dict[str, str]] = []
    for p in prompts:
        verdict, severity = judge(p)
        if verdict == p["expected_verdict"] and severity == p["expected_severity"]:
            passed += 1
        else:
            failures.append(
                {
                    "id": p["id"],
                    "got_verdict": verdict,
                    "got_severity": severity,
                    "expected_verdict": p["expected_verdict"],
                    "expected_severity": p["expected_severity"],
                }
            )
    duration_s = time.perf_counter() - started
    summary: dict[str, Any] = {
        "total": len(prompts),
        "pass": passed,
        "fail": len(failures),
        "duration_s": round(duration_s, 3),
    }
    if failures:
        summary["failures"] = failures
    print(json.dumps(summary, sort_keys=True))
    if failures:
        return 1
    if duration_s >= budget_s:
        print(f"eval_smoke FAIL: duration {duration_s:.2f}s ≥ {budget_s}s budget", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _parse_args(argv)
    try:
        _require_mock_mode()
    except NotImplementedError as exc:
        print(f"eval_smoke FAIL: {exc}", file=sys.stderr)
        return 1
    return _run(args.dataset, args.max_duration)


if __name__ == "__main__":
    sys.exit(main())

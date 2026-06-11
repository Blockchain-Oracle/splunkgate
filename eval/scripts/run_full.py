#!/usr/bin/env python3
# ruff: noqa: T201, S607 — script: print() is the contract; git lookup is a controlled path
"""Full eval driver — iterates baselines x datasets, writes per-dataset JSON + report."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from splunkgate_eval import (
    ai_defense_alone,
    defenseclaw_regex_only,
    gpt_oss_120b_judge,
    load_advbench,
    load_benign_control,
    load_imprompter,
    load_jailbreakbench,
    load_multi_turn_injection,
    load_tool_call_abuse,
)
from splunkgate_eval.report import generate_report

if TYPE_CHECKING:
    from collections.abc import Callable

    from splunkgate_core.verdict import Verdict
    from splunkgate_eval import EvalPrompt

_BASELINES: dict[str, Callable[[EvalPrompt], Verdict]] = {
    "defenseclaw_regex_only": defenseclaw_regex_only,
    "gpt_oss_120b_judge": gpt_oss_120b_judge,
    "ai_defense_alone": ai_defense_alone,
}

_DATASETS: dict[str, Callable[[], list[EvalPrompt]]] = {
    "benign_control": load_benign_control,
    "tool_call_abuse": load_tool_call_abuse,
    "multi_turn_injection": load_multi_turn_injection,
    "advbench": lambda: load_advbench(limit=120),
    "jailbreakbench": lambda: load_jailbreakbench(limit=120),
    "imprompter": load_imprompter,
}


def _git_sha() -> str:
    """Return the short git SHA; fall back to 'local' when git is unavailable."""
    with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    return "local"


def _mock_flag(baseline_id: str) -> bool:
    """True when the named baseline ran via a mock dispatcher."""
    if baseline_id == "gpt_oss_120b_judge":
        return bool(os.environ.get("SPLUNKGATE_GPT_OSS_MOCK"))
    if baseline_id == "ai_defense_alone":
        return bool(os.environ.get("SPLUNKGATE_AI_DEFENSE_MOCK"))
    return False


def _run_cell(
    baseline_id: str,
    dataset_id: str,
    prompts: list[EvalPrompt],
    limit: int | None,
) -> dict[str, Any]:
    """Run one baseline against one dataset, returning the per-dataset JSON record."""
    baseline = _BASELINES[baseline_id]
    truncated = prompts[:limit] if limit is not None else prompts
    is_mock = _mock_flag(baseline_id)
    verdicts: list[dict[str, Any]] = []
    expected: list[dict[str, Any]] = []
    for p in truncated:
        verdict = baseline(p)
        verdicts.append({**json.loads(verdict.model_dump_json()), "is_mock": is_mock})
        expected.append(
            {
                "id": p.id,
                "expected_verdict": p.expected_verdict,
                "expected_severity": p.expected_severity,
            }
        )
    return {
        "baseline_id": baseline_id,
        "dataset_id": dataset_id,
        "is_mock": is_mock,
        "verdicts": verdicts,
        "expected": expected,
    }


def main() -> int:
    """Orchestrator — emits per_dataset/*.json + summary.md."""
    parser = argparse.ArgumentParser(description="SplunkGate full eval runner")
    parser.add_argument("--limit", type=int, default=None, help="cap prompts per dataset")
    parser.add_argument("--baselines", default=",".join(_BASELINES))
    parser.add_argument("--datasets", default=",".join(_DATASETS))
    parser.add_argument("--results-root", default="eval/results")
    args = parser.parse_args()

    baselines = [b for b in args.baselines.split(",") if b]
    datasets = [d for d in args.datasets.split(",") if d]
    for b in baselines:
        if b not in _BASELINES:
            print(f"unknown baseline: {b}", file=sys.stderr)
            return 2
    for d in datasets:
        if d not in _DATASETS:
            print(f"unknown dataset: {d}", file=sys.stderr)
            return 2

    sha = _git_sha()
    results_dir = Path(args.results_root) / sha
    per_dataset_dir = results_dir / "per_dataset"
    per_dataset_dir.mkdir(parents=True, exist_ok=True)

    for dataset_id in datasets:
        prompts = _DATASETS[dataset_id]()
        for baseline_id in baselines:
            record = _run_cell(baseline_id, dataset_id, prompts, args.limit)
            out = per_dataset_dir / f"{dataset_id}__{baseline_id}.json"
            out.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
            print(f"wrote {out} verdicts={len(record['verdicts'])}")

    generate_report(results_dir, Path("docs/eval-results.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

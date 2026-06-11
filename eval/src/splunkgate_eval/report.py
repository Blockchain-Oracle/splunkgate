"""Render the eval headline markdown table + per-evaluator reliability/latency PNGs.

`generate_report(results_dir, output_path)` reads every
`<results_dir>/per_dataset/*.json` produced by `run_full.py`, computes
metrics + latency + cost per (evaluator, dataset), and writes
`<results_dir>/summary.md` + a mirror to `output_path` (default
`docs/eval-results.md`).

Per-row markdown shape per `docs/eval-spec.md`:
    | Evaluator | Precision | Recall | F1 | ECE | p50 ms | p99 ms | $/1k |

Per-evaluator PNGs: `<results_dir>/{reliability,latency}/<evaluator>.png`.
Deterministic ordering: baselines alphabetical, datasets alphabetical,
records sorted by `id` within a dataset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from splunkgate_eval.cost import CostSummary, cost_per_1k_verdicts
from splunkgate_eval.latency import LatencySummary, percentile_plot, percentiles
from splunkgate_eval.metrics import expected_calibration_error, f1, precision, recall
from splunkgate_eval.reliability import reliability_diagram

__all__ = ["BLOCK_VERDICTS", "Bucket", "Row", "generate_report"]


@dataclass
class Bucket:
    """Accumulated labels, predictions, probabilities, and latencies for one baseline."""

    y_true: list[int] = field(default_factory=list)
    y_pred: list[int] = field(default_factory=list)
    probas: list[float] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    is_mock: bool = False


BLOCK_VERDICTS = {"BLOCK", "MODIFY"}  # any non-ALLOW we treat as "alerted" for P/R/F1

_FOOTER = (
    "\n\n[^imprompter]: Per arxiv:2410.14923 (Fu et al., UCSD+NTU 2024), the\n"
    "    Imprompter PII-exfil pattern was patched by Mistral on 2024-09-13 at\n"
    "    the renderer layer (markdown-image rendering disabled). SplunkGate\n"
    "    detects the payload pattern in LLM output for defense-in-depth, not\n"
    "    as the sole defense.\n"
    "[^msj]: Per Anthropic Many-Shot Jailbreaking — the power-law exponent\n"
    "    is invariant to SFT/RL. We sit on the same probabilistic scaling\n"
    "    curve. This is a probabilistic gate, not a deterministic one.\n"
)


@dataclass(frozen=True)
class Row:
    """One row in the headline eval table."""

    evaluator: str
    precision: float
    recall: float
    f1: float
    ece: float
    p50_ms: float
    p99_ms: float
    cost: CostSummary
    is_mock: bool
    latency_summary: LatencySummary


def _iter_per_dataset(per_dataset_dir: Path) -> list[dict[str, object]]:
    """Read every per-dataset JSON in deterministic (filename) order."""
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(per_dataset_dir.glob("*.json"))
    ]


def _binarise(label: str) -> int:
    """1 if SplunkGate would have alerted (BLOCK/MODIFY), 0 otherwise."""
    return 1 if label in BLOCK_VERDICTS else 0


def _proba_for(label: str) -> float:
    """Probability proxy: 1.0 on BLOCK, 0.5 on MODIFY/REVIEW, 0.0 on ALLOW."""
    if label == "BLOCK":
        return 1.0
    if label in {"MODIFY", "REVIEW"}:
        return 0.5
    return 0.0


def _gather(per_dataset: list[dict[str, object]]) -> dict[str, Bucket]:
    """Group per-dataset records by baseline_id (concatenating across datasets)."""
    by_baseline: dict[str, Bucket] = {}
    for record in per_dataset:
        baseline_id = str(record["baseline_id"])
        bucket = by_baseline.setdefault(baseline_id, Bucket())
        bucket.is_mock = bucket.is_mock or bool(record.get("is_mock", False))
        verdicts = list(record["verdicts"]) if isinstance(record["verdicts"], list) else []
        expected = list(record["expected"]) if isinstance(record["expected"], list) else []
        for v, e in zip(verdicts, expected, strict=True):
            v_dict = v if isinstance(v, dict) else {}
            e_dict = e if isinstance(e, dict) else {}
            bucket.y_true.append(_binarise(str(e_dict.get("expected_verdict", ""))))
            label = str(v_dict.get("verdict", ""))
            bucket.y_pred.append(_binarise(label))
            bucket.probas.append(_proba_for(label))
            bucket.latencies_ms.append(float(v_dict.get("latency_ms", 0.0)))
    return by_baseline


def _row(baseline_id: str, bucket: Bucket) -> Row:
    """Compute one Row from the gathered bucket."""
    lat = percentiles(bucket.latencies_ms)
    return Row(
        evaluator=baseline_id,
        precision=precision(bucket.y_true, bucket.y_pred),
        recall=recall(bucket.y_true, bucket.y_pred),
        f1=f1(bucket.y_true, bucket.y_pred),
        ece=expected_calibration_error(bucket.y_true, bucket.probas),
        p50_ms=lat.p50,
        p99_ms=lat.p99,
        cost=cost_per_1k_verdicts(baseline_id, len(bucket.y_true)),
        is_mock=bucket.is_mock,
        latency_summary=lat,
    )


def _format_cost(cost: CostSummary) -> str:
    """Render a dollar amount or the human-readable note when None."""
    return f"${cost.dollars_per_1k:.3f}" if cost.dollars_per_1k is not None else cost.note


def _render_table(rows: list[Row]) -> str:
    """Render the headline pipe-separated markdown table."""
    header = (
        "| Evaluator | Precision | Recall | F1 | ECE | p50 latency (ms) | "
        "p99 latency (ms) | $/1k verdicts |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    body_lines: list[str] = []
    for r in sorted(rows, key=lambda x: x.evaluator):
        evaluator = f"{r.evaluator} (mock)" if r.is_mock else r.evaluator
        # Latency rounded to 1 decimal — perf_counter timing varies microseconds
        # across consecutive runs; .1f makes the markdown byte-identical across
        # idempotent invocations.
        body_lines.append(
            f"| {evaluator} | {r.precision:.3f} | {r.recall:.3f} | "
            f"{r.f1:.3f} | {r.ece:.3f} | {r.p50_ms:.1f} | {r.p99_ms:.1f} | "
            f"{_format_cost(r.cost)} |",
        )
    return header + "\n".join(body_lines) + "\n"


def generate_report(
    results_dir: Path,
    output_path: Path = Path("docs/eval-results.md"),
) -> None:
    """Render summary.md + mirror to `output_path`; write per-evaluator PNGs."""
    per_dataset = _iter_per_dataset(results_dir / "per_dataset")
    by_baseline = _gather(per_dataset)
    rows = [_row(bid, bucket) for bid, bucket in sorted(by_baseline.items())]
    rel_dir = results_dir / "reliability"
    lat_dir = results_dir / "latency"
    for bid, bucket in sorted(by_baseline.items()):
        reliability_diagram(bucket.y_true, bucket.probas, rel_dir / f"{bid}.png")
        percentile_plot(bucket.latencies_ms, lat_dir / f"{bid}.png")
    table = _render_table(rows)
    mock_note = (
        "> Rows marked `(mock)` ran against deterministic mock dispatchers — "
        "the underlying upstream call was NOT made. Do not interpret these "
        "rows as production benchmarks.\n\n"
        if any(r.is_mock for r in rows)
        else ""
    )
    body = "# SplunkGate eval results\n\n" + mock_note + table + _FOOTER
    summary_path = results_dir / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(body, encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")

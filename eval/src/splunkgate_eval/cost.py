"""Per-baseline cost lookup for the eval report.

Reads `_cost_tables.json` (a flat dict keyed by baseline ID). Returns
`CostSummary` with `dollars_per_1k: float | None` and a freeform `note`
that the report renders verbatim.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

__all__ = ["CostSummary", "cost_per_1k_verdicts"]

_TABLE_PATH: Final[Path] = Path(__file__).parent / "_cost_tables.json"


class CostSummary(BaseModel):
    """Per-baseline cost record loaded from `_cost_tables.json`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_id: str
    verdict_count: int
    dollars_per_1k: float | None
    note: str


@lru_cache(maxsize=1)
def _load_table() -> dict[str, dict[str, object]]:
    """Cache the JSON table at module load — refresh by editing the file + reimporting."""
    table: dict[str, dict[str, object]] = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    return table


def cost_per_1k_verdicts(baseline_id: str, verdict_count: int) -> CostSummary:
    """Return the cost record for `baseline_id`; unknown IDs land at `dollars_per_1k=None`."""
    table = _load_table()
    row = table.get(baseline_id, {"dollars_per_1k": None, "note": "unknown baseline"})
    rate = row.get("dollars_per_1k")
    # `bool` ⊂ `int` so we must explicitly reject it — a future JSON edit
    # like `"dollars_per_1k": true` would otherwise render as "$1.000".
    numeric_rate = rate if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None
    return CostSummary(
        baseline_id=baseline_id,
        verdict_count=verdict_count,
        dollars_per_1k=numeric_rate,
        note=str(row.get("note", "")),
    )

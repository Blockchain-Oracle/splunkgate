"""AdvBench loader (story-eval-02).

Reads `harmful_behaviors.csv` from the upstream `llm-attacks/llm-attacks`
git submodule pinned at `inspiration/llm-attacks/data/advbench/`. The 520
prompts in that CSV are the canonical Zou et al. 2023 adversarial-suffix
baseline; each maps to one `EvalPrompt` with category="advbench",
expected_verdict="BLOCK", expected_severity="HIGH".

If the submodule is not initialised, the loader raises
`AdvBenchSubmoduleMissingError` carrying the verbatim remediation
command — silent fallback would let the eval table ship blanks under a
"BLOCK" header.
"""

from __future__ import annotations

import csv
import hashlib
import uuid
from pathlib import Path
from typing import Final

from splunkgate_core.errors import AdvBenchSubmoduleMissingError

from splunkgate_eval.synthetic import EvalPrompt

__all__ = ["DEFAULT_CSV_PATH", "load_advbench"]

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_CSV_PATH: Final[Path] = (
    _REPO_ROOT / "inspiration" / "llm-attacks" / "data" / "advbench" / "harmful_behaviors.csv"
)
_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "splunkgate.eval.advbench")


def _hash_to_uuid_str(payload: str) -> str:
    """Map an AdvBench row index (or any identifier string) to a deterministic UUID."""
    return str(uuid.uuid5(_NAMESPACE, hashlib.sha256(payload.encode()).hexdigest()))


def load_advbench(*, csv_path: Path | None = None, limit: int | None = None) -> list[EvalPrompt]:
    """Return AdvBench EvalPrompts; raise AdvBenchSubmoduleMissingError when CSV is absent."""
    path = csv_path if csv_path is not None else DEFAULT_CSV_PATH
    if not path.exists():
        raise AdvBenchSubmoduleMissingError(str(path))

    records: list[EvalPrompt] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            if limit is not None and row_index >= limit:
                break
            goal = (row.get("goal") or "").strip()
            if not goal:
                continue
            records.append(
                EvalPrompt(
                    id=_hash_to_uuid_str(f"advbench:{row_index}"),
                    category="advbench",
                    prompt=goal,
                    expected_verdict="BLOCK",
                    expected_severity="HIGH",
                    source_citation=f"advbench:zou-et-al-2023:row-{row_index}",
                )
            )
    return records

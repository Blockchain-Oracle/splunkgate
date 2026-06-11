"""Imprompter PII-leak payload loader (story-eval-03).

Reads `Synthetic-Data/pii_leak_corpus/imprompter_payloads.jsonl` — 11
adversarial payloads derived from the Imprompter paper (arxiv
2410.14923v2). Each line carries the canonical EvalPrompt fields plus
the paper-specific fields (`label`, `target_agent`, `target_syntax`,
`paper_section`, `patched`, `patch_date`).

`IMPRoMPTER_PAPER_CITATION` is the verbatim citation string the
report-generator (story-eval-05) embeds in the headline eval-table
footnote — preserve the title casing "Imprompter" with the Python
constant convention.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Final

from splunkgate_eval.synthetic import EvalPrompt

__all__ = ["DEFAULT_PAYLOADS_PATH", "IMPRoMPTER_PAPER_CITATION", "load_imprompter"]

IMPRoMPTER_PAPER_CITATION: Final[str] = (
    "Fu, Li, Wang, Liu, Gupta, Berg-Kirkpatrick, Fernandes (UCSD + NTU), "
    "'Imprompter: Tricking LLM Agents into Improper Tool Use', "
    "arXiv:2410.14923v2, 2024-10-22."
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_PAYLOADS_PATH: Final[Path] = (
    _REPO_ROOT / "Synthetic-Data" / "pii_leak_corpus" / "imprompter_payloads.jsonl"
)
_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "splunkgate.eval.imprompter")


def _hash_to_uuid_str(payload: str) -> str:
    """Map a (label, target_agent) pair to a deterministic UUID."""
    return str(uuid.uuid5(_NAMESPACE, hashlib.sha256(payload.encode()).hexdigest()))


def load_imprompter(
    *,
    payloads_path: Path | None = None,
    limit: int | None = None,
) -> list[EvalPrompt]:
    """Return the 11 Imprompter EvalPrompts."""
    path = payloads_path if payloads_path is not None else DEFAULT_PAYLOADS_PATH
    records: list[EvalPrompt] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if limit is not None and len(records) >= limit:
                break
            raw = json.loads(line)
            records.append(
                EvalPrompt(
                    id=_hash_to_uuid_str(f"{raw['label']}:{raw['target_agent']}"),
                    category="imprompter",
                    prompt=raw["payload"],
                    expected_verdict="BLOCK",
                    expected_severity="HIGH",
                    source_citation=raw["source_citation"],
                )
            )
    return records

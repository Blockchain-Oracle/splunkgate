"""MockAIDefenseClient — deterministic in-memory dispatcher matching the live client surface.

Same async `inspect_chat` interface as `aegis_judges.ai_defense.AIDefenseClient` so
downstream consumers (middleware, MCP server, eval harness) accept either
implementation behind a `Protocol`-like duck-typed signature.

Dispatch order:
  1. Exact match on the trigger string (with `[tier:*]` suffix) — kept for unit tests.
  2. Substring scan against the tier-stripped trigger phrase — used in demos so a
     user typing the bare phrase ("import os; os.system('rm -rf /')") gets the
     highest-severity fixture for that phrase rather than a hash-bucket misfire.
  3. Fallback — controlled by `dispatch_mode`:
       - "substring" (default, demo-safe) → return `_default_safe` (no false positives).
       - "hash" (eval-only opt-in) → SHA-256 bucket into the matrix for variation.

Fixture matrix loaded from `_fixtures/ai_defense_matrix.json` at construction
time. Contains 44 rows: 11 canonical Cisco AI Defense rules x 4 severities.

§14 carve-out per architecture.md "Submission checklist gates": this filename
ends in `_mock.py`; the §14 grep rule excludes such files. Trigger strings
inside are intentional synthetic data, not production hot-path code.
"""

import hashlib
import re
from typing import Literal, Self

import structlog

from aegis_judges._fixtures import load_fixture_matrix, load_trigger_table
from aegis_judges.ai_defense_types import (
    InspectRequest,
    InspectResponse,
    Severity,
)

_logger = structlog.get_logger(__name__)

_TIER_SUFFIX_RE = re.compile(r"\s*\[tier:[a-z_]+\]\s*$", re.IGNORECASE)

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.NONE_SEVERITY: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
}


class MockAIDefenseClient:
    """Same async surface as AIDefenseClient; returns deterministic fixtures."""

    def __init__(
        self,
        *,
        dispatch_mode: Literal["substring", "hash"] = "substring",
    ) -> None:
        """Load fixtures and build the substring index.

        `dispatch_mode="substring"` (default) is demo-safe: unknown text returns
        a clean ALLOW. `dispatch_mode="hash"` is for the eval harness: unknown
        text gets deterministically bucketed for variation.
        """
        self._matrix: list[InspectResponse] = load_fixture_matrix()
        self._triggers: dict[str, int] = load_trigger_table()
        self._dispatch_mode = dispatch_mode
        self._phrase_index: dict[str, int] = self._build_phrase_index()
        self._default_safe: InspectResponse = InspectResponse(
            is_safe=True,
            severity=Severity.NONE_SEVERITY,
        )

    def _build_phrase_index(self) -> dict[str, int]:
        """Map tier-stripped phrase → matrix index of its highest-severity fixture.

        When the matrix has the same phrase at multiple severities (the canonical
        4-tier-per-rule shape), demos should see the most dramatic verdict, so
        we pick HIGH > MEDIUM > LOW > NONE.
        """
        best: dict[str, tuple[int, int]] = {}
        for trigger, idx in self._triggers.items():
            phrase = _TIER_SUFFIX_RE.sub("", trigger).strip().lower()
            if not phrase:
                continue
            rank = _SEVERITY_RANK.get(self._matrix[idx].severity, 0)
            current = best.get(phrase)
            if current is None or rank > current[0]:
                best[phrase] = (rank, idx)
        return {phrase: idx for phrase, (_, idx) in best.items()}

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        """Dispatch on request.messages[-1].content → fixture; fallback per mode."""
        text = request.messages[-1].content if request.messages else ""
        response = self._dispatch(text)
        _logger.debug(
            "aidefense.mock.hit",
            trace_id=trace_id,
            severity=response.severity.value,
            is_safe=response.is_safe,
            matched=text in self._triggers,
            mode=self._dispatch_mode,
        )
        return response

    async def aclose(self) -> None:
        """No-op; mock holds no network resources."""

    async def __aenter__(self) -> Self:
        """Allow `async with MockAIDefenseClient() as c:` usage."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """No-op."""

    def _dispatch(self, text: str) -> InspectResponse:
        """Exact → substring → (mode-gated) hash → safe default."""
        if text in self._triggers:
            return self._matrix[self._triggers[text]]
        if not text.strip():
            return self._default_safe
        lowered = text.lower()
        for phrase, idx in self._phrase_index.items():
            if phrase and phrase in lowered:
                return self._matrix[idx]
        if self._dispatch_mode == "hash":
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % len(self._matrix)
            return self._matrix[idx]
        return self._default_safe

"""MockAIDefenseClient — deterministic in-memory dispatcher matching the live client surface.

Same async `inspect_chat` interface as `aegis_judges.ai_defense.AIDefenseClient` so
downstream consumers (middleware, MCP server, eval harness) accept either
implementation behind a `Protocol`-like duck-typed signature.

Dispatch is deterministic: same trigger text → same fixture, always. Stable
across process restarts (no PYTHONHASHSEED dependency).

Fixture matrix loaded from `_fixtures/ai_defense_matrix.json` at construction
time. Contains 44 rows: 11 canonical Cisco AI Defense rules x 4 severities.

§14 carve-out per architecture.md "Submission checklist gates": this filename
ends in `_mock.py`; the §14 grep rule excludes such files. Trigger strings
inside are intentional synthetic data, not production hot-path code.
"""

import hashlib
from typing import Self

import structlog

from aegis_judges._fixtures import load_fixture_matrix, load_trigger_table
from aegis_judges.ai_defense_types import (
    InspectRequest,
    InspectResponse,
    Severity,
)

_logger = structlog.get_logger(__name__)


class MockAIDefenseClient:
    """Same async surface as AIDefenseClient; returns deterministic fixtures."""

    def __init__(self) -> None:
        """Load the fixture matrix + trigger table once per instance."""
        self._matrix: list[InspectResponse] = load_fixture_matrix()
        self._triggers: dict[str, int] = load_trigger_table()
        self._default_safe: InspectResponse = InspectResponse(
            is_safe=True,
            severity=Severity.NONE_SEVERITY,
        )

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        """Dispatch on request.messages[-1].content → fixture; fallback to safe."""
        text = request.messages[-1].content if request.messages else ""
        response = self._dispatch(text)
        _logger.debug(
            "aidefense.mock.hit",
            trace_id=trace_id,
            severity=response.severity.value,
            is_safe=response.is_safe,
            matched=text in self._triggers,
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
        """Lookup fixture by exact trigger; fallback to deterministic hash-bucketing."""
        if text in self._triggers:
            return self._matrix[self._triggers[text]]
        if not text.strip():
            return self._default_safe
        # Hash-bucket unmatched text into the matrix for variation in eval runs.
        # SHA-256 keeps dispatch stable across processes (PYTHONHASHSEED-independent).
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % len(self._matrix)
        return self._matrix[idx]

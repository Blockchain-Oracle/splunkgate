"""Live AIDefense integration test — gated on `SPLUNKGATE_AI_DEFENSE_API_KEY`.

Skipped when the env var is unset or whitespace-only (so the standard
test run is unaffected). When set, runs exactly ONE request against the
real Cisco Explorer Edition endpoint to confirm shape compliance. ONE
request per CI invocation only — quota protection per `docs/judges-spec.md`
(10M queries / app / year).

Whitespace and invalid-region handling are LOUD, not silent (PR #127
review): we strip the API key (matching `ai_defense.py:from_env`), and
fail rather than coerce an invalid region to `"us"`.
"""

from __future__ import annotations

import os

import pytest
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import (
    InspectMessage,
    InspectRequest,
    InspectResponse,
    Severity,
)

_GATE_VAR = "SPLUNKGATE_AI_DEFENSE_API_KEY"
_VALID_REGIONS = {"us", "eu", "ap", "fed"}
# Strip whitespace at module import so whitespace-only env vars (a common
# CI misconfiguration shape) gate the test correctly.
_RAW_KEY = os.environ.get(_GATE_VAR, "").strip()
_REASON = f"{_GATE_VAR} unset or whitespace-only"


@pytest.mark.asyncio
@pytest.mark.skipif(not _RAW_KEY, reason=_REASON)
async def test_live_inspect_chat_shape() -> None:
    """Single live request — assert the response shape, not the verdict outcome."""
    region_raw = os.environ.get("SPLUNKGATE_AI_DEFENSE_REGION", "us").strip().lower()
    if region_raw and region_raw not in _VALID_REGIONS:
        pytest.fail(
            f"SPLUNKGATE_AI_DEFENSE_REGION={region_raw!r} is not a known region "
            f"{sorted(_VALID_REGIONS)}; fix the env var rather than silently using 'us'."
        )
    region = region_raw or "us"
    async with AIDefenseClient(_RAW_KEY, region=region) as client:  # type: ignore[arg-type]
        resp = await client.inspect_chat(
            InspectRequest(messages=[InspectMessage(role="user", content="hello")])
        )
    assert isinstance(resp, InspectResponse)
    assert isinstance(resp.is_safe, bool)
    assert resp.severity in set(Severity)

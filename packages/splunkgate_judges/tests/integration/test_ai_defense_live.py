"""Live AIDefense integration test — gated on `SPLUNKGATE_AI_DEFENSE_API_KEY`.

Skipped when the env var is unset (so the standard test run is unaffected).
When set, runs exactly ONE request against the real Cisco Explorer Edition
endpoint to confirm shape compliance. ONE request per CI invocation only —
quota protection per `docs/judges-spec.md` (10M queries / app / year).
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
_REASON = f"{_GATE_VAR} unset"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get(_GATE_VAR), reason=_REASON)
async def test_live_inspect_chat_shape() -> None:
    """Single live request — assert the response shape, not the verdict outcome."""
    api_key = os.environ[_GATE_VAR]
    region = os.environ.get("SPLUNKGATE_AI_DEFENSE_REGION", "us").lower()
    if region not in {"us", "eu", "ap", "fed"}:
        region = "us"
    async with AIDefenseClient(api_key, region=region) as client:  # type: ignore[arg-type]
        resp = await client.inspect_chat(
            InspectRequest(messages=[InspectMessage(role="user", content="hello")])
        )
    # Shape compliance only — don't assume content of the verdict.
    assert isinstance(resp, InspectResponse)
    assert isinstance(resp.is_safe, bool)
    assert resp.severity in set(Severity)

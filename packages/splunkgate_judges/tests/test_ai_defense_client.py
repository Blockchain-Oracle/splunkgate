"""Behavioral tests for AIDefenseClient.

respx intercepts all httpx traffic — no real network calls escape.
"""

import json

import httpx
import pytest
import respx
from splunkgate_judges._errors import (
    AIDefenseAuthError,
    AIDefenseTimeoutError,
    AIDefenseUpstreamError,
)
from splunkgate_judges._regions import REGION_BASE_URLS
from splunkgate_judges.ai_defense import AIDefenseClient
from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    InspectMessage,
    InspectRequest,
)

API_KEY = "ai-def-synth-1234567890abcdefghij"
HAPPY_RESPONSE = {
    "is_safe": False,
    "severity": "HIGH",
    "classifications": ["SECURITY_VIOLATION", "PRIVACY_VIOLATION"],
    "rules": [
        {
            "rule_name": "PII",
            "classification": "PRIVACY_VIOLATION",
            "entity_types": ["SSN"],
        }
    ],
    "attack_technique": "data_exfiltration",
    "explanation": "The user message contains a US SSN.",
    "event_id": "evt_abc",
    "client_transaction_id": "tx_xyz",
}


@pytest.fixture(autouse=True)
def _patch_tenacity_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real wait_exponential_jitter sleeps so retry tests run in ms."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)


def _sample_request() -> InspectRequest:
    return InspectRequest(
        messages=[InspectMessage(role="user", content="My ssn is 123-45-6789")],
    )


@pytest.mark.asyncio
async def test_happy_path_parses_inspect_response_with_us_region() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            resp = await client.inspect_chat(_sample_request())
            assert route.called
            assert resp.severity.value == "HIGH"
            assert resp.rules[0].rule_name is AIDefenseRule.PII
            assert resp.rules[0].classification is Classification.PRIVACY_VIOLATION


@pytest.mark.asyncio
async def test_auth_header_uses_x_cisco_ai_defense_api_key() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            await client.inspect_chat(_sample_request())
            assert route.calls.last.request.headers["X-Cisco-AI-Defense-API-Key"] == API_KEY


@pytest.mark.parametrize("region", ["us", "eu", "ap", "fed"])
@pytest.mark.asyncio
async def test_regional_routing_hits_correct_base_url(region: str) -> None:
    url = REGION_BASE_URLS[region] + "/api/v1/inspect/chat"  # type: ignore[index]
    async with AIDefenseClient(API_KEY, region=region) as client:  # type: ignore[arg-type]
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            await client.inspect_chat(_sample_request())
            assert route.called
            assert (
                route.calls.last.request.url.host
                == f"{region}.api.inspect.aidefense.security.cisco.com"
            )


@pytest.mark.asyncio
async def test_503_retried_then_succeeds() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(
                side_effect=[
                    httpx.Response(503),
                    httpx.Response(503),
                    httpx.Response(200, json=HAPPY_RESPONSE),
                ]
            )
            resp = await client.inspect_chat(_sample_request())
            assert route.call_count == 3
            assert resp.severity.value == "HIGH"


@pytest.mark.asyncio
async def test_401_raises_auth_error_no_retry() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(
                return_value=httpx.Response(401, json={"message": "Unauthorized"})
            )
            with pytest.raises(AIDefenseAuthError):
                await client.inspect_chat(_sample_request())
            assert route.call_count == 1


@pytest.mark.asyncio
async def test_403_raises_auth_error_no_retry() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(403))
            with pytest.raises(AIDefenseAuthError):
                await client.inspect_chat(_sample_request())
            assert route.call_count == 1


@pytest.mark.asyncio
async def test_400_raises_upstream_error_no_retry() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(
                return_value=httpx.Response(400, json={"message": "bad request"})
            )
            with pytest.raises(AIDefenseUpstreamError):
                await client.inspect_chat(_sample_request())
            assert route.call_count == 1  # 4xx not retried


@pytest.mark.asyncio
async def test_persistent_5xx_raises_upstream_error_after_retries() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(503))
            with pytest.raises(AIDefenseUpstreamError):
                await client.inspect_chat(_sample_request())
            assert route.call_count == 3


@pytest.mark.asyncio
async def test_timeout_raises_aidefense_timeout_error() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us", timeout_s=0.05) as client:
        with respx.mock() as router:
            route = router.post(url).mock(side_effect=httpx.ReadTimeout("simulated timeout"))
            with pytest.raises(AIDefenseTimeoutError):
                await client.inspect_chat(_sample_request())
            assert route.call_count == 3


@pytest.mark.asyncio
async def test_trace_id_kwarg_does_not_raise() -> None:
    """trace_id passed to inspect_chat should flow through without error."""
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            router.post(url).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            resp = await client.inspect_chat(_sample_request(), trace_id="abc-123")
            assert resp.severity.value == "HIGH"


@pytest.mark.asyncio
async def test_request_body_is_inspect_request_json_shape() -> None:
    url = REGION_BASE_URLS["us"] + "/api/v1/inspect/chat"
    async with AIDefenseClient(API_KEY, region="us") as client:
        with respx.mock() as router:
            route = router.post(url).mock(return_value=httpx.Response(200, json=HAPPY_RESPONSE))
            await client.inspect_chat(_sample_request())
            sent = json.loads(route.calls.last.request.content.decode("utf-8"))
            assert "messages" in sent
            assert sent["messages"][0]["role"] == "user"
            assert sent["messages"][0]["content"] == "My ssn is 123-45-6789"

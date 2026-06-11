"""In-process FastAPI fake of the Cisco AI Defense Inspection API.

POST /api/v1/inspect/chat — mirrors the real endpoint shape verbatim per
`packages/splunkgate_judges/src/splunkgate_judges/ai_defense_types.py`.
The fake exists so end-to-end tests cover the AIDefenseClient → wire →
fake → response path without hitting the live Cisco endpoint (10M
queries/year quota burn protection — see judges-03 docstrings).

Failure-mode dispatch via the `X-Fake-AIDefense-Policy` header. Policies:
- "happy"        (default): 200 with a deterministic safe-response body
- "pii"                   : 200 with a HIGH-severity PII verdict body
- "503-twice"             : 503 on the first two attempts (per api-key),
                            200 on the third
- "503-always"            : 503 always
- "401"                   : 401 always (auth failure)
- "timeout"               : sleep longer than any reasonable client timeout

The server runs inside a background asyncio task bound to an ephemeral
port. FastAPI is banned in the SplunkGate runtime per architecture.md
(MCP runtime context), but permitted in tests/integration/.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    InspectResponse,
    RuleHit,
    Severity,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_HAPPY_PII_RESPONSE = InspectResponse(
    is_safe=False,
    severity=Severity.HIGH,
    classifications=[Classification.PRIVACY_VIOLATION],
    rules=[
        RuleHit(
            rule_name=AIDefenseRule.PII,
            classification=Classification.PRIVACY_VIOLATION,
            entity_types=["SSN"],
        ),
    ],
    attack_technique="data_exfiltration",
    explanation="The user message contains a US SSN.",
    event_id="evt_fake_happy",
    client_transaction_id="tx_fake_happy",
)

_HAPPY_SAFE_RESPONSE = InspectResponse(
    is_safe=True,
    severity=Severity.NONE_SEVERITY,
    classifications=[],
    rules=[],
    attack_technique=None,
    explanation=None,
    event_id="evt_fake_safe",
    client_transaction_id="tx_fake_safe",
)


def _pick_free_port() -> int:
    """Return an OS-assigned free TCP port. Subject to TOCTOU; acceptable for tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_app() -> tuple[FastAPI, dict[str, int]]:
    """Build the FastAPI app + return its per-api-key 503 counter dict."""
    app = FastAPI(title="Fake AI Defense")
    counter: dict[str, int] = {}

    @app.post("/api/v1/inspect/chat")
    async def inspect_chat(
        request: Request,
        x_fake_aidefense_policy: Annotated[str, Header()] = "",
    ) -> InspectResponse:
        """Dispatch by header OR by API-key value (since AIDefenseClient
        sends the key verbatim and doesn't expose a custom-header hook,
        tests can encode the policy as the API key — e.g. `api_key="pii"`).
        """
        await request.body()
        api_key = request.headers.get("x-cisco-ai-defense-api-key", "")
        policy = x_fake_aidefense_policy or api_key or "happy"
        if policy == "401":
            raise HTTPException(status_code=401, detail="bad api key")
        if policy == "timeout":
            await asyncio.sleep(30.0)
            return _HAPPY_SAFE_RESPONSE
        if policy == "503-twice":
            count = counter.get(api_key, 0)
            counter[api_key] = count + 1
            if count < 2:
                raise HTTPException(status_code=503, detail="upstream")
            return _HAPPY_SAFE_RESPONSE
        if policy == "503-always":
            raise HTTPException(status_code=503, detail="upstream")
        if policy == "pii":
            return _HAPPY_PII_RESPONSE
        return _HAPPY_SAFE_RESPONSE

    return app, counter


@asynccontextmanager
async def fake_ai_defense_server() -> AsyncIterator[str]:
    """Start the fake on an ephemeral port; yield the base URL.

    Wait-for-ready polls the port for up to 2 seconds before yielding.
    Tear-down cancels the uvicorn task.
    """
    app, _counter = _build_app()
    port = _pick_free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    # Race the started-flag wait against the task itself. If serve()
    # crashes during startup (port conflict that survived
    # `_pick_free_port`'s TOCTOU window, ImportError, etc.), the task
    # finishes with an exception; without this race the generic
    # "failed to start within 2s" would hide the real cause.
    started_check = asyncio.create_task(_wait_started(server))
    try:
        done, _pending = await asyncio.wait(
            {task, started_check},
            timeout=2.0,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        started_check.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await started_check
    if task in done:
        # serve() exited before startup completed — propagate the real exception.
        msg = "uvicorn serve() exited before startup completed"
        raise RuntimeError(msg) from task.exception()
    if not server.started:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        msg = "fake AI Defense server failed to start within 2s"
        raise RuntimeError(msg)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        # Surface any server-side exception so it isn't lost on teardown.
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                msg = "fake server raised during teardown"
                raise RuntimeError(msg) from exc


async def _wait_started(server: uvicorn.Server) -> None:
    """Poll uvicorn's `started` flag at 10ms intervals. Caller bounds the timeout.

    uvicorn does not expose an asyncio.Event for startup readiness, so a
    polling loop is unavoidable here. ruff's ASYNC110 suggestion to use
    `asyncio.Event` doesn't apply.
    """
    while not server.started:  # noqa: ASYNC110
        await asyncio.sleep(0.01)

# ruff: noqa: INP001 — examples/ is intentionally not a package
# §14 CARVE-OUT: this is the test double for the verification harness, not a production code path.
"""Minimal Splunk HEC double for the docker-compose smoke (story-dc-01).

Accepts POST /services/collector/event, appends each event to
$DOUBLE_HEC_EVENTS_PATH as a JSON line, returns Splunk's canonical
`{"text":"Success","code":0}` envelope. ≤80 LOC.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aiohttp import web

_EVENTS_PATH = Path(os.environ.get("DOUBLE_HEC_EVENTS_PATH", "/data/events.jsonl"))


async def health(_request: web.Request) -> web.Response:
    """Splunk HEC health endpoint — returns 200 with the canonical text shape."""
    return web.json_response({"text": "HEC is healthy", "code": 17})


async def collector_event(request: web.Request) -> web.Response:
    """Accept any HEC payload; append to the JSONL spool; return Splunk's envelope.

    Failure modes are visible: malformed JSON → 400 with Splunk's canonical
    code 6; spool write failure (OSError — full disk, permission denied,
    bad mount) → log to stderr and still return 200 so DefenseClaw's
    circuit breaker doesn't open on a test-double infrastructure issue.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"text": "Invalid data format", "code": 6}, status=400)

    try:
        _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _EVENTS_PATH.open("a", encoding="utf-8") as handle:  # noqa: ASYNC230 — single-process test double; bounded line write
            handle.write(json.dumps(body, sort_keys=True))
            handle.write("\n")
    except OSError as exc:
        print(  # noqa: T201
            f"hec_double: spool write failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    return web.json_response({"text": "Success", "code": 0})


def build_app() -> web.Application:
    """Wire the two HEC routes."""
    app = web.Application()
    app.router.add_get("/services/collector/health", health)
    app.router.add_post("/services/collector/event", collector_event)
    return app


def main() -> None:
    """Run the mock on `DOUBLE_HEC_PORT` (default 8088)."""
    port = int(os.environ.get("DOUBLE_HEC_PORT", "8088"))
    web.run_app(build_app(), host="0.0.0.0", port=port, access_log=None)  # noqa: S104 — container-scoped


if __name__ == "__main__":
    main()

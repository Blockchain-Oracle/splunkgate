"""`python -m splunkgate_mcp` entry point.

Chooses between stdio and HTTP transport based on `resolve_transport()`
which reads `SPLUNKGATE_MCP_TRANSPORT`. Supports `--version` for cheap
liveness checks (used by the test harness + the Splunk app heartbeat).
"""

from __future__ import annotations

import asyncio
import sys

from splunkgate_core.errors import ConfigError, SplunkGateError

import splunkgate_mcp
from splunkgate_mcp.server import resolve_transport, serve_http, serve_stdio


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Returns the process exit code.

    Honours the `-> int` contract on the failure paths too:
    - `ConfigError` (bad SPLUNKGATE_MCP_TRANSPORT) → clean stderr line + exit 2
    - serve_*() failure → clean stderr line + exit 1
    Operators see actionable diagnostics, not raw Python tracebacks
    (silent-failure-hunter review on PR #115 flagged the prior behavior).
    """
    args = list(argv if argv is not None else sys.argv[1:])

    if "--version" in args:
        sys.stdout.write(f"splunkgate-mcp {splunkgate_mcp.__version__}\n")
        return 0

    try:
        transport = resolve_transport()
    except ConfigError as exc:
        sys.stderr.write(f"splunkgate-mcp: configuration error: {exc}\n")
        return 2

    try:
        if transport == "stdio":
            asyncio.run(serve_stdio())
        else:
            asyncio.run(serve_http())
    except SplunkGateError as exc:
        sys.stderr.write(f"splunkgate-mcp: server failed: {exc}\n")
        return 1
    except KeyboardInterrupt:
        # Ctrl-C during stdio session — clean shutdown, not an error.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

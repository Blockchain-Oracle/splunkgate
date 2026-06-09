"""`python -m splunkgate_mcp` entry point.

Chooses between stdio and HTTP transport based on `resolve_transport()`
which reads `SPLUNKGATE_MCP_TRANSPORT`. Supports `--version` for cheap
liveness checks (used by the test harness + the Splunk app heartbeat).
"""

from __future__ import annotations

import asyncio
import sys

import splunkgate_mcp
from splunkgate_mcp.server import resolve_transport, serve_http, serve_stdio


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Returns the process exit code."""
    args = list(argv if argv is not None else sys.argv[1:])

    if "--version" in args:
        sys.stdout.write(f"splunkgate-mcp {splunkgate_mcp.__version__}\n")
        return 0

    transport = resolve_transport()
    if transport == "stdio":
        asyncio.run(serve_stdio())
    else:
        asyncio.run(serve_http())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

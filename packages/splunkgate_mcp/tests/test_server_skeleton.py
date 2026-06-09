"""Behavioral tests for story-mcp-01: SplunkGate MCP server skeleton."""

from __future__ import annotations

import inspect
import subprocess
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
import splunkgate_mcp
from splunkgate_core.errors import ConfigError
from splunkgate_core.verdict import Severity, Verdict, VerdictLabel
from splunkgate_mcp import __main__ as splunkgate_mcp_main
from splunkgate_mcp._test_helpers import list_tools_for_test
from splunkgate_mcp.otel import MCP_PROTOCOL_VERSION, build_span_attributes
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_mcp.server import (
    _REGISTERED_TOOLS,
    HTTP_BIND_HOST,
    HTTP_BIND_PORT,
    _is_allowed_origin,
    build_http_app,
    ensure_ping_registered,
    register_tool,
    resolve_transport,
    serve_stdio,
    server,
)
from starlette.testclient import TestClient


def test_version_is_0_1_0() -> None:
    """Package version bumped from 0.0.1 stub to 0.1.0 first-real-skeleton."""
    assert splunkgate_mcp.__version__ == "0.1.0"


def test_verdict_output_schema_matches_pydantic() -> None:
    """schemas.VERDICT_OUTPUT_SCHEMA must equal Verdict.model_json_schema()."""
    assert Verdict.model_json_schema() == VERDICT_OUTPUT_SCHEMA


def test_otel_span_attributes_contains_required_keys() -> None:
    """build_span_attributes returns dict with the 3 required keys."""
    attrs = build_span_attributes(session_id="abc123", method_name="tools/call")

    assert attrs["mcp.method.name"] == "tools/call"
    assert attrs["mcp.session.id"] == "abc123"
    assert attrs["mcp.protocol.version"] == "2025-11-25"


def test_otel_span_attributes_protocol_version_is_2025_11_25() -> None:
    """MCP protocol version is the Stable 2025-11-25 (NOT 2025-03-26)."""
    assert MCP_PROTOCOL_VERSION == "2025-11-25"


def test_server_module_imports_official_mcp_sdk() -> None:
    """The `server` instance is from the official `mcp` SDK, not a fork."""
    assert type(server).__module__.startswith("mcp.")


def test_register_tool_uses_fastmcp_derived_schemas() -> None:
    """register_tool sources schemas from FastMCP, not from kwargs.

    This is the wire-truth contract: RegisteredTool.outputSchema reflects
    what MCP clients see, not what we passed in. Test fn returns a Verdict
    so FastMCP derives VERDICT_OUTPUT_SCHEMA correctly.
    """
    _REGISTERED_TOOLS.clear()
    # Also clear FastMCP's internal registry so re-registration doesn't collide
    server._tool_manager._tools.pop("_test_tool", None)  # noqa: SLF001

    async def typed_fn() -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mcp_score",
            latency_ms=0.0,
        )

    register_tool(name="_test_tool", fn=typed_fn, description="Test tool")

    assert "_test_tool" in _REGISTERED_TOOLS
    entry = _REGISTERED_TOOLS["_test_tool"]
    assert entry.name == "_test_tool"
    # FastMCP derived the schema from the typed return — must equal VERDICT_OUTPUT_SCHEMA
    assert entry.outputSchema == VERDICT_OUTPUT_SCHEMA
    assert callable(entry.fn)


def test_list_tools_for_test_returns_registered_tools() -> None:
    """_test_helpers exposes the internal registry without async FastMCP surface."""
    _REGISTERED_TOOLS.clear()
    server._tool_manager._tools.pop("_helper_test", None)  # noqa: SLF001

    async def typed_fn() -> Verdict:
        return Verdict(
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            verdict=VerdictLabel.ALLOW,
            severity=Severity.NONE_SEVERITY,
            rules=[],
            surface="mcp_score",
            latency_ms=0.0,
        )

    register_tool(name="_helper_test", fn=typed_fn, description="x")

    tools = list_tools_for_test()
    names = [t.name for t in tools]
    assert "_helper_test" in names
    target = next(t for t in tools if t.name == "_helper_test")
    assert target.outputSchema == VERDICT_OUTPUT_SCHEMA


def test_ping_tool_registered_at_bootstrap() -> None:
    """_ping no-op tool registers automatically with VERDICT_OUTPUT_SCHEMA."""
    ensure_ping_registered()

    assert "_ping" in _REGISTERED_TOOLS
    ping = _REGISTERED_TOOLS["_ping"]
    assert ping.outputSchema == VERDICT_OUTPUT_SCHEMA


def test_resolve_transport_defaults_to_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPLUNKGATE_MCP_TRANSPORT unset → stdio (per MCP spec default)."""
    monkeypatch.delenv("SPLUNKGATE_MCP_TRANSPORT", raising=False)
    assert resolve_transport() == "stdio"


def test_resolve_transport_http_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPLUNKGATE_MCP_TRANSPORT=http → http (Streamable HTTP opt-in)."""
    monkeypatch.setenv("SPLUNKGATE_MCP_TRANSPORT", "http")
    assert resolve_transport() == "http"


def test_resolve_transport_invalid_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid SPLUNKGATE_MCP_TRANSPORT raises ConfigError at startup, not first message."""
    monkeypatch.setenv("SPLUNKGATE_MCP_TRANSPORT", "ftp")
    with pytest.raises(ConfigError, match="SPLUNKGATE_MCP_TRANSPORT"):
        resolve_transport()


def test_serve_stdio_is_async_callable() -> None:
    """serve_stdio is an async function that wraps FastMCP.run_stdio_async."""
    assert inspect.iscoroutinefunction(serve_stdio)


def test_http_constants_are_127_0_0_1_and_8765() -> None:
    """HTTP transport binds 127.0.0.1:8765 (locked per MCP DNS-rebind guidance)."""
    assert HTTP_BIND_HOST == "127.0.0.1"
    assert HTTP_BIND_PORT == 8765


@pytest.fixture
def reset_session_manager() -> Generator[None]:
    """Reset FastMCP's one-shot session manager between HTTP origin tests.

    `StreamableHTTPSessionManager.run()` is a one-shot — each test that
    builds the HTTP app needs a fresh session manager or the second
    `build_http_app()` call dies with "can only be called once per
    instance". Production calls `build_http_app` exactly once at startup,
    so this reset stays out of the production code path (per Task 9
    simplification review).
    """
    server._session_manager = None  # noqa: SLF001 — test isolation
    yield
    server._session_manager = None  # noqa: SLF001 — leave clean


@pytest.mark.usefixtures("reset_session_manager")
def test_http_origin_header_rejects_cross_origin() -> None:
    """HTTP POST with cross-origin Origin returns 403 per MCP DNS-rebind mitigation."""
    app = build_http_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        headers={"Origin": "https://attacker.example"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 403


@pytest.mark.usefixtures("reset_session_manager")
def test_http_origin_header_accepts_localhost() -> None:
    """HTTP POST with localhost Origin passes the check (status != 403)."""
    app = build_http_app()
    # `with` context manager triggers the FastMCP streamable-HTTP lifespan
    # which initialises its anyio task group — without it the MCP handler
    # raises RuntimeError before any status code is returned.
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            headers={"Origin": "http://127.0.0.1:3000"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
    # Origin accepted → status NOT 403 (may be 200/406/415/421 depending on
    # MCP handshake state — but Origin was accepted, that's what we test)
    assert resp.status_code != 403


@pytest.mark.usefixtures("reset_session_manager")
def test_http_origin_header_missing_is_rejected() -> None:
    """HTTP POST without Origin returns 403 per MCP DNS-rebind requirement.

    Per security review M1: stdio-bridge clients use STDIO transport, NOT
    HTTP. Any HTTP request without Origin is either a misconfigured client
    or a malicious actor attempting DNS rebinding via Origin omission
    (e.g. `fetch(url, {mode:'no-cors'})` or non-CORS form POST). The MCP
    spec mandates Origin validation on every HTTP request.
    """
    app = build_http_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 403


def test_main_module_has_callable_main() -> None:
    """`python -m splunkgate_mcp` dispatches via a main() function."""
    assert hasattr(splunkgate_mcp_main, "main")
    assert callable(splunkgate_mcp_main.main)


def test_main_module_version_flag_exits_clean() -> None:
    """`python -m splunkgate_mcp --version` exits 0 with version in stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "splunkgate_mcp", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "0.1.0" in result.stdout, f"stdout: {result.stdout!r}"


# --- Origin parser edge cases (PR #115 review findings) -----------------
# Tests below exercise `_is_allowed_origin` directly because spinning up
# `build_http_app` per case is expensive + already covered by the 3 main
# Origin tests above. These tests catch the parser bugs the toolkit
# code-reviewer flagged: IPv6 bracket parsing, scheme allowlist, null.


def test_origin_ipv6_localhost_accepted() -> None:
    """IPv6 localhost `http://[::1]:8080` is accepted (urlsplit handles brackets).

    Code-reviewer caught: the old parser split on first `:` after stripping
    the scheme, producing host `"["` for `[::1]:8080`. The allowlist
    contained `"[::1]"` but the parser could never produce it — silent
    functional break for IPv6 clients. urllib.parse.urlsplit.hostname
    returns the bracket-less form (`"::1"`), and the allowlist now matches.
    """

    assert _is_allowed_origin("http://[::1]:8080") is True
    assert _is_allowed_origin("http://[::1]") is True


def test_origin_file_scheme_rejected() -> None:
    """`file://localhost/etc/passwd` is rejected — only http(s) is allowed.

    Browsers can emit `file://` from local HTML; MCP DNS-rebind threat
    model assumes http(s) only, so other schemes get 403.
    """

    assert _is_allowed_origin("file://localhost/etc/passwd") is False


def test_origin_null_literal_rejected() -> None:
    """`Origin: null` (sandboxed iframe) is rejected — no scheme to validate."""

    assert _is_allowed_origin("null") is False


def test_origin_whitespace_normalized() -> None:
    """Trailing/leading whitespace is stripped before parsing (RFC 7230 OWS)."""

    assert _is_allowed_origin("  http://127.0.0.1:3000  ") is True
    assert _is_allowed_origin("  ") is False  # empty after strip


def test_origin_attacker_host_rejected() -> None:
    """Suffix attacks like `http://127.0.0.1.attacker.com` are rejected."""

    assert _is_allowed_origin("http://127.0.0.1.attacker.com") is False
    assert _is_allowed_origin("http://localhost.attacker.com") is False

# Story — SplunkGate MCP Server skeleton with official `mcp` Python SDK

**ID:** story-mcp-01-server-skeleton-with-mcp-python-sdk
**Epic:** EPIC-07 — Surface 2 SplunkGate MCP Server (own server, parallel to Splunk's)
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** safety-net developer wiring SplunkGate to MCP clients (Claude Desktop, Cursor, any home-built agent)
**I want to** stand up an own MCP server skeleton built on the official `mcp` Python SDK, with stdio (default) + streamable-HTTP (env-toggled) transports, a registry pattern that downstream tool-stories plug into, and OTel `mcp.method.name`/`mcp.session.id` attributes on every span
**So that** stories `mcp-02` through `mcp-05` have a single load-bearing surface to register against, and every SplunkGate tool call surfaces on the same OTel + Splunk audit trail as Surface 1 verdicts — without coupling to Splunk's closed-source MCP Server

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/splunkgate_mcp/pyproject.toml` — NEW — workspace member, deps on `splunkgate-core`, `mcp` (official Python SDK), `pydantic>=2`, `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-util-genai`, `structlog`
- `packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py` — NEW — empty package marker with `__version__ = "0.1.0"`
- `packages/splunkgate_mcp/src/splunkgate_mcp/server.py` — NEW — FastMCP-style server registration via official `mcp` SDK; instantiates `FastMCP("splunkgate-mcp")`; exposes `register_tool(name, fn, input_schema, output_schema)` registry helper backed by an internal `_REGISTERED_TOOLS: dict[str, RegisteredTool]` mapping (the registry IS the source of truth that `_test_helpers.list_tools_for_test()` reads); `serve_stdio()` and `serve_http()` entrypoints chosen by `SPLUNKGATE_MCP_TRANSPORT` env var (defaults to `stdio`); HTTP path binds to `127.0.0.1` only and validates `Origin` header per MCP spec
- `packages/splunkgate_mcp/src/splunkgate_mcp/_test_helpers.py` — NEW — test-only helper module exporting `def list_tools_for_test() -> list[RegisteredTool]` which returns the values of the internal `_REGISTERED_TOOLS` registry from `server.py`. Used by mcp-02 through mcp-05 BDD tests as the canonical way to enumerate registered tools without depending on the official `mcp` SDK's `FastMCP` surface (which exposes tools via async protocol methods, not a sync registry call). `RegisteredTool` is the dataclass-or-Pydantic shape produced by `register_tool` with at minimum `.name`, `.outputSchema`, `.input_schema`, and `.fn` attributes
- `packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py` — NEW — exports `VERDICT_OUTPUT_SCHEMA = Verdict.model_json_schema()` from `splunkgate_core.verdict.Verdict`
- `packages/splunkgate_mcp/src/splunkgate_mcp/otel.py` — NEW — OTel helper that wraps each tool invocation in a `mcp.server` span (SERVER kind) tagged with `mcp.method.name="tools/call"`, `mcp.session.id`, `mcp.protocol.version="2025-11-25"`, and co-emits `gen_ai.evaluation.result` events via `splunkgate_core.otel`
- `packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py` — NEW — `python -m splunkgate_mcp` entrypoint that calls `server.serve_stdio()` or `server.serve_http()` based on env var
- `packages/splunkgate_mcp/tests/__init__.py` — NEW — empty
- `packages/splunkgate_mcp/tests/test_server_skeleton.py` — NEW — ≥ 10 behavioral tests: server instantiates, `register_tool` adds to internal registry, `tools/list` returns registered names, `tools/call` round-trips a no-op `_ping` tool returning a `Verdict` shape, `outputSchema` on registered tool equals `VERDICT_OUTPUT_SCHEMA`, OTel span emitted on each call has `mcp.method.name="tools/call"`, transport defaults to stdio when env unset, HTTP transport binds to `127.0.0.1`, Origin-header rejection returns 403 on cross-origin POST, MCP protocol version reported is `2025-11-25`

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/splunkgate_mcp/src/splunkgate_mcp/server.py imports the official `mcp` Python SDK
When  `uv run python -c "import mcp; from splunkgate_mcp.server import server; print(type(server).__module__)"` runs
Then  the output starts with "mcp." (the FastMCP instance is from the official SDK, not a fork)

Given the server registry is empty by default
When  the no-op `_ping` tool is registered via `register_tool("_ping", ...)` with `outputSchema=VERDICT_OUTPUT_SCHEMA`
Then  `tools/list` over the in-process JSON-RPC harness returns exactly one tool named `_ping`
And   the returned tool record's `outputSchema` field deep-equals `Verdict.model_json_schema()`

Given `_ping` is registered
When  `uv run python -c "from splunkgate_mcp._test_helpers import list_tools_for_test; tools = list_tools_for_test(); names=[t.name for t in tools]; assert '_ping' in names, names; print('OK')"` runs
Then  exit code is 0
And   stdout contains "OK"

Given `_ping` is registered with `outputSchema=VERDICT_OUTPUT_SCHEMA`
When  `list_tools_for_test()` is called from a test
Then  the entry for `_ping` exposes `.outputSchema` deep-equal to `Verdict.model_json_schema()`

Given the server is invoked with SPLUNKGATE_MCP_TRANSPORT unset
When  `uv run python -c "from splunkgate_mcp.server import resolve_transport; print(resolve_transport())"` runs
Then  the output is "stdio"

Given the server is invoked with SPLUNKGATE_MCP_TRANSPORT=http
When  `uv run python -c "from splunkgate_mcp.server import resolve_transport; import os; os.environ['SPLUNKGATE_MCP_TRANSPORT']='http'; print(resolve_transport())"` runs
Then  the output is "http"

Given a tool call hits the server
When  the OTel span is recorded by the in-test exporter
Then  the span's `mcp.method.name` attribute equals "tools/call"
And   the span has a non-empty `mcp.session.id` attribute
And   the span has `mcp.protocol.version` equal to "2025-11-25"

Given the HTTP transport is started bound to 127.0.0.1
When  a POST arrives with `Origin: https://attacker.example`
Then  the server returns HTTP 403 (DNS-rebinding mitigation per MCP spec)

Given the test file exists
When  `uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the server.py source
When  `wc -l packages/splunkgate_mcp/src/splunkgate_mcp/server.py` runs
Then  the line count is ≤ 400

Given the §14 grep runs on production code
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Server skeleton imports cleanly and exposes the expected public API
uv run python -c "
from splunkgate_mcp.server import server, register_tool, resolve_transport, serve_stdio, serve_http
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from splunkgate_core.verdict import Verdict
assert VERDICT_OUTPUT_SCHEMA == Verdict.model_json_schema()
assert resolve_transport() == 'stdio'  # default
print('OK')
"
# Must print 'OK'

# Test helper exposes the registry without going through the FastMCP async protocol surface
uv run python -c "
from splunkgate_mcp._test_helpers import list_tools_for_test
# After _ping is registered at server bootstrap, list_tools_for_test() returns it
tools = list_tools_for_test()
assert any(t.name == '_ping' for t in tools), [t.name for t in tools]
print('OK')
"
# Must print 'OK'

# `mcp` SDK is the official one
uv run python -c "import mcp, mcp.server; print('official mcp:', mcp.__name__)"
# Must print 'official mcp: mcp'

# Tests pass
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# OTel attribute presence smoke
uv run python -c "
from splunkgate_mcp.otel import build_span_attributes
attrs = build_span_attributes(session_id='abc123', method_name='tools/call')
assert attrs['mcp.method.name'] == 'tools/call'
assert attrs['mcp.session.id'] == 'abc123'
assert attrs['mcp.protocol.version'] == '2025-11-25'
print('OK')
"
# Must print 'OK'

# 400-LOC cap on every new source file
for f in packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/otel.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py; do
  wc -l "$f" | awk '{ if ($1 > 400) { print "OVERFLOW " $0; exit 1 } }'
done
# Must exit 0

# §14 clean on production code (test fixtures are §14 carve-outs)
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source (CiscoDevNet repo is README+LICENSE only, multi-confirmed).** We run our OWN MCP server alongside, NOT registering into theirs. SplunkGate tools use the `splunkgate_*` prefix exclusively. They coexist with Splunk's 10 native `splunk_*` tools and 4 `saia_*` tools (when SAIA is co-installed) via standard MCP client multi-server configs.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP spec 2025-11-25 is Stable; tools support `structuredContent` + `outputSchema` for rich validated verdicts.** Every SplunkGate tool's `outputSchema` is derived from Pydantic via `Verdict.model_json_schema()` — protocol-level validation at the MCP server boundary catches schema drift.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, the two standard transports are stdio (preferred) and Streamable HTTP.** stdio is the default per the spec: "Clients SHOULD support stdio whenever possible." HTTP transport MUST validate the `Origin` header (DNS-rebinding mitigation) and SHOULD bind only to `127.0.0.1` when running locally.
- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`, `mcp.protocol.version`, `mcp.resource.uri`) co-emit with `gen_ai.evaluation.result` events.** Use a SERVER-kind span named `{mcp.method.name} {tool_name}` per the semconv span-name guidance. Reuse `splunkgate_core.otel` for the evaluation event emission — do not duplicate emitter logic here.
- Use the official `mcp` Python SDK's `FastMCP` server pattern — it provides `@server.tool()` decorators and the registry primitives. Do NOT roll your own JSON-RPC router; the SDK already implements the protocol.
- The `register_tool(...)` helper in `server.py` is the public registry entrypoint for stories `mcp-02` through `mcp-05`. Keep the signature stable: `(name: str, fn: Callable, input_schema: dict, output_schema: dict, description: str)`.
- `SPLUNKGATE_MCP_TRANSPORT` env var values: `stdio` (default), `http`. Anything else → raise `splunkgate_core.errors.SplunkGateConfigError`.
- The MCP protocol version we declare on initialization is the current Stable: `"2025-11-25"`. Do NOT hardcode `"2025-03-26"` (that's what Splunk's older MCP Server reports per the CiscoDevNet README).
- Banned per `docs/architecture.md`: `flask`, `django`, `fastapi` for the MCP server. Use the official `mcp` SDK only.
- The `_ping` no-op tool exists only for skeleton-level tests and stays in the package after stories `mcp-02..05` land — it's the cheapest health-probe surface for the Splunk app's dashboard heartbeat.
- **`asyncio.run(server.list_tools())` does NOT work against the official `mcp` SDK's `FastMCP` surface** — `FastMCP.list_tools` is exposed via the MCP protocol's `tools/list` method, not as a sync registry call. Downstream stories (mcp-02 through mcp-05) MUST use `from splunkgate_mcp._test_helpers import list_tools_for_test` instead. The helper reads the internal `_REGISTERED_TOOLS` dict that `register_tool` populates, which IS the source of truth for what the server exposes via the protocol surface.

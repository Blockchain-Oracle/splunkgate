# Story — Aegis MCP Server skeleton with official `mcp` Python SDK

**ID:** story-mcp-01-server-skeleton-with-mcp-python-sdk
**Epic:** EPIC-07 — Surface 2 Aegis MCP Server (own server, parallel to Splunk's)
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** safety-net developer wiring Aegis to MCP clients (Claude Desktop, Cursor, any home-built agent)
**I want to** stand up an own MCP server skeleton built on the official `mcp` Python SDK, with stdio (default) + streamable-HTTP (env-toggled) transports, a registry pattern that downstream tool-stories plug into, and OTel `mcp.method.name`/`mcp.session.id` attributes on every span
**So that** stories `mcp-02` through `mcp-05` have a single load-bearing surface to register against, and every Aegis tool call surfaces on the same OTel + Splunk audit trail as Surface 1 verdicts — without coupling to Splunk's closed-source MCP Server

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mcp/pyproject.toml` — NEW — workspace member, deps on `aegis-core`, `mcp` (official Python SDK), `pydantic>=2`, `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-util-genai`, `structlog`
- `packages/aegis_mcp/src/aegis_mcp/__init__.py` — NEW — empty package marker with `__version__ = "0.1.0"`
- `packages/aegis_mcp/src/aegis_mcp/server.py` — NEW — FastMCP-style server registration via official `mcp` SDK; instantiates `FastMCP("aegis-mcp")`; exposes `register_tool(name, fn, input_schema, output_schema)` registry helper; `serve_stdio()` and `serve_http()` entrypoints chosen by `AEGIS_MCP_TRANSPORT` env var (defaults to `stdio`); HTTP path binds to `127.0.0.1` only and validates `Origin` header per MCP spec
- `packages/aegis_mcp/src/aegis_mcp/schemas.py` — NEW — exports `VERDICT_OUTPUT_SCHEMA = Verdict.model_json_schema()` from `aegis_core.verdict.Verdict`
- `packages/aegis_mcp/src/aegis_mcp/otel.py` — NEW — OTel helper that wraps each tool invocation in a `mcp.server` span (SERVER kind) tagged with `mcp.method.name="tools/call"`, `mcp.session.id`, `mcp.protocol.version="2025-11-25"`, and co-emits `gen_ai.evaluation.result` events via `aegis_core.otel`
- `packages/aegis_mcp/src/aegis_mcp/__main__.py` — NEW — `python -m aegis_mcp` entrypoint that calls `server.serve_stdio()` or `server.serve_http()` based on env var
- `packages/aegis_mcp/tests/__init__.py` — NEW — empty
- `packages/aegis_mcp/tests/test_server_skeleton.py` — NEW — ≥ 10 behavioral tests: server instantiates, `register_tool` adds to internal registry, `tools/list` returns registered names, `tools/call` round-trips a no-op `_ping` tool returning a `Verdict` shape, `outputSchema` on registered tool equals `VERDICT_OUTPUT_SCHEMA`, OTel span emitted on each call has `mcp.method.name="tools/call"`, transport defaults to stdio when env unset, HTTP transport binds to `127.0.0.1`, Origin-header rejection returns 403 on cross-origin POST, MCP protocol version reported is `2025-11-25`

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/aegis_mcp/src/aegis_mcp/server.py imports the official `mcp` Python SDK
When  `uv run python -c "import mcp; from aegis_mcp.server import server; print(type(server).__module__)"` runs
Then  the output starts with "mcp." (the FastMCP instance is from the official SDK, not a fork)

Given the server registry is empty by default
When  the no-op `_ping` tool is registered via `register_tool("_ping", ...)` with `outputSchema=VERDICT_OUTPUT_SCHEMA`
Then  `tools/list` over the in-process JSON-RPC harness returns exactly one tool named `_ping`
And   the returned tool record's `outputSchema` field deep-equals `Verdict.model_json_schema()`

Given the server is invoked with AEGIS_MCP_TRANSPORT unset
When  `uv run python -c "from aegis_mcp.server import resolve_transport; print(resolve_transport())"` runs
Then  the output is "stdio"

Given the server is invoked with AEGIS_MCP_TRANSPORT=http
When  `uv run python -c "from aegis_mcp.server import resolve_transport; import os; os.environ['AEGIS_MCP_TRANSPORT']='http'; print(resolve_transport())"` runs
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
When  `uv run pytest packages/aegis_mcp/tests/test_server_skeleton.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given the server.py source
When  `wc -l packages/aegis_mcp/src/aegis_mcp/server.py` runs
Then  the line count is ≤ 400

Given the §14 grep runs on production code
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Server skeleton imports cleanly and exposes the expected public API
uv run python -c "
from aegis_mcp.server import server, register_tool, resolve_transport, serve_stdio, serve_http
from aegis_mcp.schemas import VERDICT_OUTPUT_SCHEMA
from aegis_core.verdict import Verdict
assert VERDICT_OUTPUT_SCHEMA == Verdict.model_json_schema()
assert resolve_transport() == 'stdio'  # default
print('OK')
"
# Must print 'OK'

# `mcp` SDK is the official one
uv run python -c "import mcp, mcp.server; print('official mcp:', mcp.__name__)"
# Must print 'official mcp: mcp'

# Tests pass
uv run pytest packages/aegis_mcp/tests/test_server_skeleton.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# OTel attribute presence smoke
uv run python -c "
from aegis_mcp.otel import build_span_attributes
attrs = build_span_attributes(session_id='abc123', method_name='tools/call')
assert attrs['mcp.method.name'] == 'tools/call'
assert attrs['mcp.session.id'] == 'abc123'
assert attrs['mcp.protocol.version'] == '2025-11-25'
print('OK')
"
# Must print 'OK'

# 400-LOC cap on every new source file
for f in packages/aegis_mcp/src/aegis_mcp/server.py \
         packages/aegis_mcp/src/aegis_mcp/schemas.py \
         packages/aegis_mcp/src/aegis_mcp/otel.py \
         packages/aegis_mcp/src/aegis_mcp/__main__.py; do
  wc -l "$f" | awk '{ if ($1 > 400) { print "OVERFLOW " $0; exit 1 } }'
done
# Must exit 0

# §14 clean on production code (test fixtures are §14 carve-outs)
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mcp/src/
# Must output nothing
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source (CiscoDevNet repo is README+LICENSE only, multi-confirmed).** We run our OWN MCP server alongside, NOT registering into theirs. Aegis tools live under names like `aegis_*` / `sentinel_*` and coexist with Splunk's `splunk_*` and `saia_*` tools via standard MCP client multi-server configs.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP spec 2025-11-25 is Stable; tools support `structuredContent` + `outputSchema` for rich validated verdicts.** Every Aegis tool's `outputSchema` is derived from Pydantic via `Verdict.model_json_schema()` — protocol-level validation at the MCP server boundary catches schema drift.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, the two standard transports are stdio (preferred) and Streamable HTTP.** stdio is the default per the spec: "Clients SHOULD support stdio whenever possible." HTTP transport MUST validate the `Origin` header (DNS-rebinding mitigation) and SHOULD bind only to `127.0.0.1` when running locally.
- **Per `../../../context/10-standards/02-otel-genai-semantic-conventions.md`, MCP sub-convention attrs (`mcp.method.name`, `mcp.session.id`, `mcp.protocol.version`, `mcp.resource.uri`) co-emit with `gen_ai.evaluation.result` events.** Use a SERVER-kind span named `{mcp.method.name} {tool_name}` per the semconv span-name guidance. Reuse `aegis_core.otel` for the evaluation event emission — do not duplicate emitter logic here.
- Use the official `mcp` Python SDK's `FastMCP` server pattern — it provides `@server.tool()` decorators and the registry primitives. Do NOT roll your own JSON-RPC router; the SDK already implements the protocol.
- The `register_tool(...)` helper in `server.py` is the public registry entrypoint for stories `mcp-02` through `mcp-05`. Keep the signature stable: `(name: str, fn: Callable, input_schema: dict, output_schema: dict, description: str)`.
- `AEGIS_MCP_TRANSPORT` env var values: `stdio` (default), `http`. Anything else → raise `aegis_core.errors.AegisConfigError`.
- The MCP protocol version we declare on initialization is the current Stable: `"2025-11-25"`. Do NOT hardcode `"2025-03-26"` (that's what Splunk's older MCP Server reports per the CiscoDevNet README).
- Banned per `docs/architecture.md`: `flask`, `django`, `fastapi` for the MCP server. Use the official `mcp` SDK only.
- The `_ping` no-op tool exists only for skeleton-level tests and stays in the package after stories `mcp-02..05` land — it's the cheapest health-probe surface for the Splunk app's dashboard heartbeat.

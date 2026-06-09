# Cursor IDE integration

This page is a paste-ready config for Cursor IDE. Two transports are
documented: stdio (default per MCP spec — "Clients SHOULD support stdio
whenever possible", `../../../context/10-standards/01-mcp-spec-deep.md`),
and Streamable HTTP (native; Cursor reads `url` + `headers` keys directly,
unlike Claude Desktop which needs the `mcp-remote` bridge).

The config file lives at:

- Per-project: `.cursor/mcp.json` at the project root
- Per-user: `~/.cursor/mcp.json`

Edit the file, paste the block, restart Cursor (the MCP client only re-reads
the config on launch). The four SplunkGate tools
(`splunkgate_score_prompt_injection`, `splunkgate_judge_tool_call`,
`splunkgate_check_output_leak`, `splunkgate_audit_trace`) appear in Cursor's
tool picker on next session start.

---

## Tools exposed

Each one-line description below mirrors the `description=` string the server
registers; the full `inputSchema` / `outputSchema` ships on the wire and is
viewable via `tools/list`.

- **`splunkgate_score_prompt_injection`** — score input text for prompt-injection
  risk via splunklib's cheap regex pass plus Cisco AI Defense escalation on hit.
  Returns a typed `Verdict`.
- **`splunkgate_judge_tool_call`** — judge a downstream tool invocation
  (`tool_name` + `tool_args`) through DefenseClaw's regex rule-pack before the
  agent executes it. Returns a typed `Verdict`.
- **`splunkgate_check_output_leak`** — inspect model output for PII/PHI/PCI
  leaks via Cisco AI Defense. On MODIFY/BLOCK, `modifications.redacted_output`
  carries the same text with leaks replaced by `[REDACTED:<rule>]` tokens.
- **`splunkgate_audit_trace`** — aggregate every SplunkGate verdict for a given
  `trace_id` by querying Splunk REST for the `cisco_ai_defense:splunkgate_verdict`
  sourcetype. Returns a typed `AuditReport`.

---

## Stdio (default)

Paste this verbatim into `.cursor/mcp.json`. The same JSON lives at
[`_examples/splunkgate-mcp-stdio.json`](./_examples/splunkgate-mcp-stdio.json).

```json
{
  "mcpServers": {
    "splunkgate-mcp-server": {
      "command": "python",
      "args": ["-m", "splunkgate_mcp"],
      "env": {
        "SPLUNKGATE_MCP_TRANSPORT": "stdio",
        "SPLUNKGATE_AI_DEFENSE_MOCK": "1",
        "SPLUNKGATE_AI_DEFENSE_REGION": "us"
      }
    }
  }
}
```

Notes:

- Cursor passes the `command` literal to the OS spawn call; on macOS / Linux
  the GUI process inherits a different `PATH` from your shell, so if `python`
  doesn't resolve, use an **absolute path** (`/usr/bin/python3.13`,
  `~/.venv/splunkgate/bin/python`, etc.) — same gotcha as Claude Desktop.
- All env vars are passed via the `env` key — Cursor does NOT forward shell
  env vars to MCP subprocesses, so anything the server needs must be listed
  explicitly here.
- `SPLUNKGATE_AI_DEFENSE_MOCK=1` selects a deterministic offline fixture
  backend so the tools light up with zero secrets.
  > **MOCK mode caveat:** verdicts under `SPLUNKGATE_AI_DEFENSE_MOCK=1` are
  > **not** real Cisco AI Defense classifications — the mock backend returns a
  > fixed rule set used for offline integration testing, and many real-world
  > injection / leak shapes will surface as `ALLOW` / `BENIGN`. To validate
  > SplunkGate against a real prompt-injection or PII payload, drop the mock
  > flag and set `SPLUNKGATE_AI_DEFENSE_API_KEY=<your-key>`.
- `splunkgate_audit_trace` additionally needs `SPLUNKGATE_SPLUNK_HOST`,
  `SPLUNKGATE_SPLUNK_USER`, `SPLUNKGATE_SPLUNK_PASSWORD` to reach Splunk REST.
  Without them the tool surfaces a `ConfigError` in-band — `isError: true`
  with `content[0].text` containing
  `ConfigError: SPLUNKGATE_SPLUNK_HOST not set (or empty); required for Splunk REST search`
  (the exact string raised by `splunkgate_judges.splunk_search._require_env`).

---

## Streamable HTTP (native)

Cursor supports the `url` + `headers` shape natively — no bridge subprocess.
Start the SplunkGate HTTP server first:

```bash
SPLUNKGATE_MCP_TRANSPORT=http \
SPLUNKGATE_AI_DEFENSE_MOCK=1 \
python -m splunkgate_mcp
# Listens on 127.0.0.1:8765/mcp — localhost-only per the MCP spec's
# DNS-rebinding mitigation.
```

Then paste this verbatim into `.cursor/mcp.json`. The same JSON lives at
[`_examples/splunkgate-mcp-http.json`](./_examples/splunkgate-mcp-http.json).

```json
{
  "mcpServers": {
    "splunkgate-mcp-server": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Origin": "http://127.0.0.1"
      }
    }
  }
}
```

The `Origin` header is required: the SplunkGate HTTP server rejects requests
without a localhost-family `Origin` per the MCP spec's DNS-rebinding
mitigation.

---

## Troubleshooting

### Cursor restart required after editing `.cursor/mcp.json`

Cursor reads MCP configs on launch. After any edit, fully quit and reopen
Cursor — a window reload is not enough. The Cursor MCP logs panel
(Settings → Cursor Settings → MCP) shows the `initialize` round-trip; the
client logs which servers it tried to start and the result of each one.

### `command` path doesn't resolve

Cursor's GUI process inherits its `PATH` from the OS launch services, not
your shell rc. If the stdio config fails to spawn with a `command not found`
or `ENOENT`, replace the literal `"command": "python"` with the absolute
path to your interpreter (`which python` in a shell tells you what to use).
The same goes for `npx` if you use the `mcp-remote` bridge.

### Environment variables don't reach the server

Cursor does **not** forward shell env vars to MCP subprocesses. Anything the
server needs at runtime — `SPLUNKGATE_AI_DEFENSE_API_KEY`,
`SPLUNKGATE_SPLUNK_HOST`, etc. — must be listed under the `env` key in
`.cursor/mcp.json`. If the stdio server starts but tool calls error in-band
with "missing API key", you've forgotten to thread the env var through.

### Debugging via Cursor's MCP logs panel

Open Cursor Settings → Cursor Settings → MCP. Each registered server has a
status indicator (green = up, red = failed) and an expandable log view that
shows the JSON-RPC `initialize` exchange and any spawn errors. This is the
fastest way to confirm whether the server registered four tools (look for
`tools/list` returning four `splunkgate_*` names plus `_ping`).

### Coexistence with Splunk's MCP Server

Cursor handles multiple `mcpServers` keys cleanly. Add both
`splunkgate-mcp-server` and `splunk-mcp-server` to the same block; the
`splunk_*`, `saia_*`, and `splunkgate_*` prefixes partition with no name
collisions. See
[`_examples/splunkgate-mcp-coexist-with-splunk.json`](./_examples/splunkgate-mcp-coexist-with-splunk.json)
and the **Coexistence with Splunk MCP Server** section of
[`README.md`](./README.md).

### `Origin not allowed` (HTTP 403)

The SplunkGate HTTP server validates the `Origin` header per MCP spec —
only localhost-family origins (`http://127.0.0.1`, `http://localhost`,
`http://[::1]` and `https://` variants) are accepted, and a missing
`Origin` is rejected. Set `"headers": {"Origin": "http://127.0.0.1"}` in
the Cursor config exactly as shown above. The rejection emits HTTP 403
with the response body `Origin not allowed` (literal string emitted by
`splunkgate_mcp.server._check_origin`).

### `isError: true` in the tool result, but no JSON-RPC error

Expected. MCP reports tool execution errors **in-band** via `isError: true`
on `CallToolResult`, not as JSON-RPC errors (which are reserved for
protocol-level failures). Verbatim from the spec
(`../../../context/10-standards/01-mcp-spec-deep.md`): "Tool Execution
Errors: Reported in tool results with `isError: true`". A SplunkGate
judge-side failure (e.g., Cisco AI Defense unreachable, or
`splunkgate_audit_trace` invoked without the Splunk env vars set) surfaces
this way. The human-readable explanation lives in **both**
`result.structuredContent` (typed) and `result.content[0].text` (string)
— older clients without `structuredContent` support keep working by reading
the text block, so always check both fields. Don't filter the in-band error
out: the explanation is what lets the LLM self-correct.

### Port 8765 already in use

The SplunkGate HTTP transport binds `127.0.0.1:8765` (chosen to not
collide with Splunk's `:8089/services/mcp`). If another process holds the
port, `uvicorn` will fail at startup with `[Errno 48] Address already in
use`. There is currently no env var to override the port; either rebind the
conflicting process or change the `HTTP_BIND_PORT` constant in
`packages/splunkgate_mcp/src/splunkgate_mcp/server.py` locally — file an
issue requesting an env-var override if you need this for a multi-tenant
or container-orchestrated deployment.

# Claude Desktop integration

This page is a paste-ready config for Anthropic's Claude Desktop. Two transports
are documented: stdio (default per MCP spec — "Clients SHOULD support stdio
whenever possible", `../../../context/10-standards/01-mcp-spec-deep.md`), and
Streamable HTTP via the `mcp-remote` bridge (Claude Desktop natively launches
stdio subprocesses only; HTTP needs the bridge — same pattern Splunk's own MCP
Server docs use per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`).

The config file lives at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Edit the file, paste the block, restart Claude Desktop. The four SplunkGate
tools (`splunkgate_score_prompt_injection`, `splunkgate_judge_tool_call`,
`splunkgate_check_output_leak`, `splunkgate_audit_trace`) appear in the tool
picker on next session start.

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

Paste this verbatim into `claude_desktop_config.json`. The same JSON lives at
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

Minimal stdio entry on one line (useful when grepping configs):
`{"command": "python", "args": ["-m", "splunkgate_mcp"]}`

Notes:

- `command` is `python`; if your `python` isn't on Claude Desktop's `PATH`,
  substitute an absolute interpreter path (`/usr/bin/python3.13`,
  `~/.venv/splunkgate/bin/python`, etc.). Claude Desktop spawns the subprocess
  with the GUI environment, not your shell environment, so `PATH` differs from
  a terminal.
- `SPLUNKGATE_AI_DEFENSE_MOCK=1` selects a deterministic offline fixture
  backend so the tools light up with zero secrets.
  > **MOCK mode caveat:** verdicts under `SPLUNKGATE_AI_DEFENSE_MOCK=1` are
  > **not** real Cisco AI Defense classifications — the mock backend returns a
  > fixed rule set used for offline integration testing, and many real-world
  > injection / leak shapes will surface as `ALLOW` / `BENIGN`. To validate
  > SplunkGate against a real prompt-injection or PII payload, drop the mock
  > flag and set `SPLUNKGATE_AI_DEFENSE_API_KEY=<your-key>`.
- `splunkgate_audit_trace` additionally needs `SPLUNKGATE_SPLUNK_HOST`,
  `SPLUNKGATE_SPLUNK_USER`, `SPLUNKGATE_SPLUNK_PASSWORD` to reach Splunk REST;
  without them the tool surfaces a `ConfigError` in-band — the failure looks
  like `isError: true` with `content[0].text` containing
  `ConfigError: SPLUNKGATE_SPLUNK_HOST not set (or empty); required for Splunk REST search`
  (the exact string raised by `splunkgate_judges.splunk_search._require_env`).
  The other three tools work without any Splunk connection.

---

## Streamable HTTP via `mcp-remote` bridge

Claude Desktop's MCP client only natively launches stdio subprocesses. To
target an HTTP MCP server (whether `splunkgate-mcp-server` running locally or
Splunk's own MCP Server at `https://<host>:8089/services/mcp`), use the
`mcp-remote` npm bridge as the `command`. The bridge speaks stdio to Claude
Desktop and Streamable HTTP to the server.

Start the SplunkGate HTTP server first:

```bash
SPLUNKGATE_MCP_TRANSPORT=http \
SPLUNKGATE_AI_DEFENSE_MOCK=1 \
python -m splunkgate_mcp
# Listens on 127.0.0.1:8765/mcp — localhost-only per the MCP spec's
# DNS-rebinding mitigation.
```

Then paste:

```json
{
  "mcpServers": {
    "splunkgate-mcp-server": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8765/mcp",
        "--header",
        "Origin: http://127.0.0.1"
      ]
    }
  }
}
```

The pure HTTP config (`url` + `headers`, no bridge) is at
[`_examples/splunkgate-mcp-http.json`](./_examples/splunkgate-mcp-http.json) —
that shape is what Cursor consumes natively; Claude Desktop needs the bridge.

---

## Troubleshooting

### Tools don't appear in Claude Desktop

Check the Claude Desktop MCP log:

```bash
tail -f ~/Library/Logs/Claude/mcp*.log
```

The log shows the `initialize` round-trip and any subprocess spawn errors.
Grep for specific signals:

```bash
# Confirm the SplunkGate subprocess started at all:
grep "splunkgate_mcp" ~/Library/Logs/Claude/mcp*.log

# Confirm which AI Defense backend was selected (mock vs live) at startup:
grep "ai_defense.startup" ~/Library/Logs/Claude/mcp*.log

# Surprising ALLOW / NONE_SEVERITY verdicts? Look for the WARN signals the
# server emits on coercion or redaction misses:
grep -E "audit_trace.coerce_miss|redaction.miss|redaction.no_pattern_for_rule" \
    ~/Library/Logs/Claude/mcp*.log
```

The most common failure is `command` (`python`) not resolving on Claude
Desktop's `PATH` — substitute an absolute interpreter path. Restart Claude
Desktop after any config edit; the client reads `claude_desktop_config.json`
on launch only.

### `Origin not allowed` (HTTP 403) on the HTTP transport

The SplunkGate HTTP server validates the `Origin` header per MCP spec §
"DNS rebinding mitigation" — only `http://127.0.0.1`, `http://localhost`, and
`http://[::1]` (plus their `https://` variants) are accepted. The `mcp-remote`
bridge sets `Origin` itself; if you're calling the server with `curl` or
another client and seeing 403, add `-H "Origin: http://127.0.0.1"`.

A missing `Origin` header is also rejected — the server requires the header on
every HTTP request because a DNS-rebinding attack omits it. The rejection
emits HTTP 403 with the response body `Origin not allowed` (literal string;
emitted by `splunkgate_mcp.server._check_origin` — grep the SplunkGate
server's stderr for that exact string to confirm the cause).

### Splunk's MCP Server is also configured

The two surfaces coexist cleanly — the `splunk_*` and `splunkgate_*` prefixes
partition with no name collisions. Use both keys side by side in the same
`mcpServers` block; see [`_examples/splunkgate-mcp-coexist-with-splunk.json`](./_examples/splunkgate-mcp-coexist-with-splunk.json)
and the **Coexistence with Splunk MCP Server** section of
[`README.md`](./README.md).

### `structuredContent` missing on an older client

MCP spec 2025-11-25 introduced `structuredContent` on `CallToolResult`. The
SDK populates it when a tool returns a typed Pydantic model (every SplunkGate
tool does). For backwards compatibility per the spec, the SDK also serializes
the same object into the `content` text block, so older clients that only
read `content[0].text` keep working — they just need to JSON-parse the text
themselves.

### `isError: true` in the result, but no JSON-RPC error

Expected. MCP reports tool execution errors **in-band** via `isError: true` on
`CallToolResult`, not as JSON-RPC errors (which are reserved for protocol-level
failures like an unknown method). Verbatim from the spec
(`../../../context/10-standards/01-mcp-spec-deep.md`):
"Tool Execution Errors: Reported in tool results with `isError: true`". A
SplunkGate judge-side failure (e.g., Cisco AI Defense unreachable, or
`splunkgate_audit_trace` invoked without the Splunk env vars set) surfaces
this way. The human-readable explanation lives in **both**
`result.structuredContent` (typed) and `result.content[0].text` (string) —
older clients without `structuredContent` support keep working by reading the
text block, so always check both fields when surfacing the error to a user
or LLM. Don't filter the in-band error out: the explanation is what lets the
LLM self-correct.

### `MCP-Protocol-Version` header missing on HTTP

Per spec, the server `SHOULD` assume protocol version `2025-03-26` if a client
sends an HTTP request without the header. The SplunkGate server uses the
official `mcp` Python SDK which performs full version negotiation during
`initialize`, so the header is set automatically on every subsequent request.
If you see this assumption fall back, the client is broken or using an old
SDK — the current spec version is **2025-11-25**.

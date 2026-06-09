# Integrations

Paste-ready config for MCP-aware hosts. SplunkGate ships its **own** MCP
server (Surface 2 of the four-surface architecture; ADR-004 in
`../architecture.md`) that runs side by side with Splunk's official MCP
Server — never registered into it.

Why a separate server: per
[`../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`](../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md),
Splunk's MCP Server (Splunkbase app 7931, currently v1.2.0) is **closed-source**
— the `CiscoDevNet/Splunk-MCP-Server-official` GitHub repo holds only a README
and a LICENSE, with no SDK, plugin hook, or registration API published. A
community safety net cannot inject tools into the official server; it has to
run alongside as a separate process. SplunkGate does exactly that, on its own
endpoint (`127.0.0.1:8765/mcp` for Streamable HTTP; subprocess pipes for
stdio), exposing four `splunkgate_*` tools — and any MCP client that already
points at Splunk's `splunk-mcp-server` can add a `splunkgate-mcp-server` block
right next to it.

## Per-client setup

- [Claude Desktop](./claude-desktop.md) — `claude_desktop_config.json`,
  stdio config, and Streamable HTTP via the `mcp-remote` bridge (Claude
  Desktop natively spawns stdio subprocesses only).
- [Cursor IDE](./cursor.md) — `.cursor/mcp.json`, stdio config, and native
  Streamable HTTP (`url` + `headers`, no bridge subprocess).

## SplunkGate tools

The Surface-2 MCP server exposes four tools. Each lives behind a typed
Pydantic input/output schema; the wire-emitted `inputSchema` / `outputSchema`
is what every conformant MCP client validates against. The one-line
descriptions below mirror the server's registered `description=` strings.

| Tool | Surface-1 middleware equivalent | What it does |
|---|---|---|
| `splunkgate_score_prompt_injection` | `splunkgate_mw.model_middleware.pre_inference_scan` | Cheap regex first pass via `splunklib.ai.security.detect_injection`, then escalation to Cisco AI Defense's Inspection API with `Prompt Injection` rule enabled. Returns a typed `Verdict`. |
| `splunkgate_judge_tool_call` | pending — see story-mw-02 (concrete `SafetyToolMiddleware.tool_middleware` is currently a pass-through stub in `splunkgate_mw._base`) | Judges a downstream tool invocation (`tool_name` + `tool_args`) before the agent executes it. Routes through DefenseClaw's local regex rule-pack (shell-injection / PII / PCI families) first; escalates ambiguous calls. |
| `splunkgate_check_output_leak` | `splunkgate_mw._post_inference.post_inference_scan` (the post-inference scan invoked from `SafetyModelMiddleware._apply_post_scan`) | Inspects model output for PII / PHI / PCI leaks via Cisco AI Defense. On `MODIFY` / `BLOCK`, `modifications.redacted_output` carries the same text with leaks replaced by `[REDACTED:<rule>]` tokens. |
| `splunkgate_audit_trace` | no Surface-1 counterpart — Surface-1 emits per-decision `gen_ai.evaluation.result` OTel events; cross-decision aggregation is the MCP tool's responsibility | Aggregates every SplunkGate verdict for a given `trace_id` by querying Splunk REST for the `cisco_ai_defense:splunkgate_verdict` sourcetype. Returns a typed `AuditReport`. |

The equivalence table is a developer-facing map: anyone who already wired the
middleware into an agent via `splunklib.ai` and is now adopting the MCP surface
sees which middleware seam corresponds to which tool.

## Transport choice

Per `../../../context/10-standards/01-mcp-spec-deep.md` (current MCP spec
version: **2025-11-25**), the protocol defines two standard transports:

1. **stdio** — the default. The MCP spec says "Clients SHOULD support stdio
   whenever possible." Newline-delimited JSON-RPC over the subprocess's stdin
   and stdout; the server's stderr is for logging only. Use this by default.
2. **Streamable HTTP** — opt-in via `SPLUNKGATE_MCP_TRANSPORT=http`. Binds
   `127.0.0.1:8765/mcp` only (per the spec's DNS-rebinding mitigation) and
   validates the `Origin` header on every request. Useful when one server
   needs to be shared across multiple MCP clients on the same box.

For HTTP, the SDK negotiates the protocol version during `initialize` and sets
the `MCP-Protocol-Version` header automatically on subsequent requests — the
example JSON files deliberately do not hardcode the version.

> **MOCK mode caveat:** the example configs set `SPLUNKGATE_AI_DEFENSE_MOCK=1`
> so a judge can paste and run without a Cisco API key. Verdicts under that
> flag are **not** real Cisco AI Defense classifications — they reflect a
> fixed offline fixture rule set. Drop the flag and set
> `SPLUNKGATE_AI_DEFENSE_API_KEY=<your-key>` to validate against real
> prompt-injection or PII payloads.

> **`splunkgate_audit_trace` precondition:** the audit-trace tool talks to
> Splunk REST and additionally requires `SPLUNKGATE_SPLUNK_HOST`,
> `SPLUNKGATE_SPLUNK_USER`, `SPLUNKGATE_SPLUNK_PASSWORD` env vars (USER +
> PASSWORD basic auth on `/services/search/jobs`, not an HEC token — wrong
> scope). Without them the tool surfaces a `ConfigError` in-band via
> `isError: true`. The tool also catches Splunk HTTP 200 responses whose
> body carries a `messages[].type == FATAL` payload (malformed SPL); without
> that catch, a broken search would masquerade as empty success.

## Example JSON files

Drop-in references that the per-client docs link to:

- [`_examples/splunkgate-mcp-stdio.json`](./_examples/splunkgate-mcp-stdio.json) — pure stdio.
- [`_examples/splunkgate-mcp-http.json`](./_examples/splunkgate-mcp-http.json) — pure HTTP (`url` + `headers`).
- [`_examples/splunkgate-mcp-coexist-with-splunk.json`](./_examples/splunkgate-mcp-coexist-with-splunk.json) — both servers in one block.

JSON-with-comments is not supported by MCP clients. Configuration notes that
would normally be inline comments (port `8765` chosen to not collide with
Splunk's `:8089/services/mcp`; substitute an absolute interpreter path if
`python` does not resolve on the GUI host's `PATH`) live in the surrounding
markdown instead.

## Coexistence with Splunk MCP Server

The three relevant surfaces in the Splunk-side MCP ecosystem use disjoint
tool-name prefixes — `splunk_`, `saia_`, `splunkgate_` — so they coexist in a
single `mcpServers` block with zero name collisions. The full inventory, per
`../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`:

**Splunk MCP Server (10 native `splunk_*` tools, Splunkbase app 7931):**

- `splunk_run_query`
- `splunk_get_info`
- `splunk_get_indexes`
- `splunk_get_index_info`
- `splunk_get_metadata`
- `splunk_get_user_info`
- `splunk_get_user_list`
- `splunk_get_kv_store_collections`
- `splunk_get_knowledge_objects`
- `splunk_run_saved_search`

**SAIA (4 `saia_*` tools, exposed only when Splunkbase app 7245 is co-installed):**

- `saia_generate_spl`
- `saia_explain_spl`
- `saia_ask_splunk_question`
- `saia_optimize_spl`

**SplunkGate (4 `splunkgate_*` tools — this surface):**

- `splunkgate_score_prompt_injection`
- `splunkgate_judge_tool_call`
- `splunkgate_check_output_leak`
- `splunkgate_audit_trace`

A judge or developer who already runs Splunk's MCP Server pastes the
SplunkGate block alongside the existing `splunk-mcp-server` entry — see
[`_examples/splunkgate-mcp-coexist-with-splunk.json`](./_examples/splunkgate-mcp-coexist-with-splunk.json)
for the exact shape. The two surfaces are conceptually partitioned: Splunk's
server gives the agent **read access to Splunk data** (`splunk_run_query`,
`saia_generate_spl`, etc.); SplunkGate gives the agent **a safety judgment
on every prompt, tool call, and output** plus an audit-trail aggregator over
the resulting verdict events in Splunk. They complement, they don't replace.

# Story — Claude Desktop + Cursor IDE MCP config examples (stdio + HTTP, with troubleshooting)

**ID:** story-mcp-06-claude-desktop-cursor-config-examples
**Epic:** EPIC-07 — Surface 2 Aegis MCP Server (own server, parallel to Splunk's)
**Depends on:** story-mcp-02-tool-score-prompt-injection, story-mcp-03-tool-judge-tool-call, story-mcp-04-tool-check-output-leak, story-mcp-05-tool-audit-trace
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** developer evaluating Aegis from outside the Splunk ecosystem (Claude Desktop user, Cursor IDE user, any MCP-aware host)
**I want to** drop a verbatim JSON config snippet into my MCP client's settings file and have Aegis's four tools (`aegis_score_prompt_injection`, `aegis_judge_tool_call`, `aegis_check_output_leak`, `aegis_audit_trace`) appear and work — with one stdio example and one HTTP example per client, plus a troubleshooting section that covers the actual failure modes
**So that** the MCP-bonus-prize pitch ("any MCP client can call us") is self-service — a judge can `cmd+,` into Claude Desktop, paste the config, and see Aegis verdicts inside Claude Desktop in under 60 seconds

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `docs/integrations/claude-desktop.md` — NEW — markdown only; one verbatim stdio JSON example targeting `python -m aegis_mcp` with `AEGIS_MCP_TRANSPORT=stdio`; one verbatim Streamable-HTTP JSON example using `npx mcp-remote` (the standard bridge pattern, same one Splunk's MCP Server docs use per `context/06-splunk-ai-stack/03-splunk-mcp-server.md`) pointed at `http://127.0.0.1:8765/mcp`; section listing all 4 tool names + 1-line descriptions; troubleshooting section covering: "tools don't appear" (check `~/Library/Logs/Claude/mcp*.log`), "Origin header rejected" (HTTP transport binds to 127.0.0.1, verify host matches), "Splunk's MCP Server also configured" (coexistence pattern — both `splunk-mcp-server` and `aegis-mcp-server` keys side-by-side), "structuredContent missing on older client" (backwards-compat — text content also returned per MCP spec), "isError in result but no JSON-RPC error" (expected — MCP reports tool errors in-band), "MCP-Protocol-Version header missing" (server defaults to 2025-11-25)
- `docs/integrations/cursor.md` — NEW — markdown only; one verbatim stdio JSON example for Cursor's `.cursor/mcp.json` settings file; one verbatim HTTP example (Cursor supports `url` + `headers` keys natively, per the Splunk MCP Server docs pattern); section listing all 4 tool names + 1-line descriptions; troubleshooting section covering: Cursor restart required after config change, `command` path must be absolute, env vars passed via `env` key, debugging via Cursor's MCP logs panel, coexistence with Splunk MCP Server config block
- `docs/integrations/README.md` — NEW — markdown only; one-paragraph index pointing at `claude-desktop.md` and `cursor.md`; one-paragraph note citing `context/06-splunk-ai-stack/03-splunk-mcp-server.md` that Splunk's MCP Server is closed-source and Aegis runs alongside, not registered into; tool-name table mapping each of the 4 Aegis tools to the matching Surface 1 middleware function (so cross-surface users see the equivalence)
- `docs/integrations/_examples/aegis-mcp-stdio.json` — NEW — pure JSON file with the stdio config (importable by README + linkable from the integration docs)
- `docs/integrations/_examples/aegis-mcp-http.json` — NEW — pure JSON file with the HTTP config
- `docs/integrations/_examples/aegis-mcp-coexist-with-splunk.json` — NEW — pure JSON file showing the coexistence pattern: both `splunk-mcp-server` and `aegis-mcp-server` keys in the same `mcpServers` block

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

**No Python files in this story.** Markdown + JSON only.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given docs/integrations/claude-desktop.md exists
When  `cat docs/integrations/claude-desktop.md` runs
Then  the output contains the substring "aegis_score_prompt_injection"
And   the substring "aegis_judge_tool_call"
And   the substring "aegis_check_output_leak"
And   the substring "aegis_audit_trace"

Given docs/integrations/claude-desktop.md exists
When  `grep -E '"command".*"python".*"-m".*"aegis_mcp"' docs/integrations/claude-desktop.md` runs
Then  the output is non-empty (stdio example present)

Given docs/integrations/claude-desktop.md exists
When  `grep -E 'mcp-remote|"url"' docs/integrations/claude-desktop.md` runs
Then  the output is non-empty (HTTP example present)

Given docs/integrations/claude-desktop.md has a "Troubleshooting" section
When  `grep -ci "troubleshooting" docs/integrations/claude-desktop.md` runs
Then  the output is ≥ 1

Given docs/integrations/cursor.md exists
When  `cat docs/integrations/cursor.md` runs
Then  the output contains "aegis_score_prompt_injection"
And   contains a stdio example with "command" key
And   contains an HTTP example with "url" key
And   contains a "Troubleshooting" heading

Given the example JSON files exist
When  `python -c "import json; json.load(open('docs/integrations/_examples/aegis-mcp-stdio.json'))"` runs
Then  exit code is 0 (valid JSON)

Given the example JSON files exist
When  `python -c "import json; json.load(open('docs/integrations/_examples/aegis-mcp-http.json'))"` runs
Then  exit code is 0

Given the example JSON files exist
When  `python -c "import json; json.load(open('docs/integrations/_examples/aegis-mcp-coexist-with-splunk.json'))"` runs
Then  exit code is 0

Given the coexistence example
When  `python -c "import json; cfg=json.load(open('docs/integrations/_examples/aegis-mcp-coexist-with-splunk.json')); print(sorted(cfg['mcpServers'].keys()))"` runs
Then  the output contains both "aegis-mcp-server" and "splunk-mcp-server"

Given the integration docs cite the closed-source-Splunk-MCP fact
When  `grep -li "closed-source" docs/integrations/README.md` runs
Then  the output is "docs/integrations/README.md" (citation present)

Given all docs are markdown
When  `find docs/integrations -name '*.py' -not -path '*/_examples/*'` runs
Then  the output is empty (no Python files in this story per spec)
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# All four tool names appear in the Claude Desktop doc
for tool in aegis_score_prompt_injection aegis_judge_tool_call aegis_check_output_leak aegis_audit_trace; do
  grep -q "$tool" docs/integrations/claude-desktop.md || { echo "MISSING tool name: $tool"; exit 1; }
done
echo "OK claude-desktop"

# All four tool names appear in the Cursor doc
for tool in aegis_score_prompt_injection aegis_judge_tool_call aegis_check_output_leak aegis_audit_trace; do
  grep -q "$tool" docs/integrations/cursor.md || { echo "MISSING tool name in cursor.md: $tool"; exit 1; }
done
echo "OK cursor"

# All example JSON files parse as valid JSON
for f in docs/integrations/_examples/aegis-mcp-stdio.json \
         docs/integrations/_examples/aegis-mcp-http.json \
         docs/integrations/_examples/aegis-mcp-coexist-with-splunk.json; do
  python -c "import json; json.load(open('$f'))" || { echo "INVALID JSON: $f"; exit 1; }
done
echo "OK JSON examples"

# Coexistence example contains both server keys
python -c "
import json
cfg = json.load(open('docs/integrations/_examples/aegis-mcp-coexist-with-splunk.json'))
servers = cfg['mcpServers']
assert 'aegis-mcp-server' in servers
assert 'splunk-mcp-server' in servers
print('OK coexist')
"

# Closed-source-Splunk citation present
grep -q "closed-source" docs/integrations/README.md || { echo "MISSING citation"; exit 1; }
echo "OK citation"

# No Python files in this story (markdown + JSON only)
[ -z "$(find docs/integrations -name '*.py' -not -path '*/_examples/*')" ] || { echo "UNEXPECTED Python files"; exit 1; }
echo "OK no python"

# Every markdown file is non-empty
for f in docs/integrations/claude-desktop.md docs/integrations/cursor.md docs/integrations/README.md; do
  [ -s "$f" ] || { echo "EMPTY file: $f"; exit 1; }
done
echo "OK non-empty"
```

---

## Notes for coding agent

- **Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, Splunk's official MCP Server is closed-source — we run our own server alongside, NOT register into it.** The coexistence example is the load-bearing artifact for this story: it shows a single MCP client config block with BOTH `splunk-mcp-server` and `aegis-mcp-server` keys, side-by-side. Judges who already have Splunk's MCP Server installed paste in our block and both work.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, MCP defines two standard transports: stdio (preferred) and Streamable HTTP.** Provide one example per transport per client. stdio is the default per the spec quote: "Clients SHOULD support stdio whenever possible."
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, the current Stable MCP protocol version is 2025-11-25.** The HTTP example MUST NOT hardcode a `MCP-Protocol-Version` header value — the SDK handles negotiation. If you mention the version in prose, cite it as "2025-11-25" (do NOT say "2025-03-26" — that's Splunk's older version per the CiscoDevNet README).
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, tool execution errors are reported in-band via `isError: true`, NOT as JSON-RPC errors.** Troubleshooting section must include the "isError in result but no JSON-RPC error" entry so users don't filter the tool error out by mistake.
- **Per `../../../context/10-standards/01-mcp-spec-deep.md`, the HTTP transport MUST validate the `Origin` header.** Troubleshooting section covers the "Origin rejected" failure mode pointing at the localhost-binding behavior from `story-mcp-01`.
- **Use Splunk's CiscoDevNet-README example as the structural template.** Per `../../../context/06-splunk-ai-stack/03-splunk-mcp-server.md`, that README shows the Claude Desktop and Cursor configs in their established shape. Mirror that shape so judges familiar with Splunk's docs feel at home. Their Claude Desktop block uses `npx mcp-remote` as the HTTP bridge — we use the same pattern for the Aegis HTTP example (because Claude Desktop natively supports stdio only; HTTP needs the `mcp-remote` bridge).
- **Tool descriptions in `docs/integrations/README.md` (the index) are one-line apiece** — no API spec; that lives in the `outputSchema` published by the server. The index is a router, not a reference.
- **Stdio example must point at the actual entrypoint from `story-mcp-01`:** `python -m aegis_mcp` with `env: {"AEGIS_MCP_TRANSPORT": "stdio"}`. If the entrypoint changed in `mcp-01`'s implementation, update both example JSON files to match — do NOT diverge from the actual code.
- **HTTP example default port is `8765`** (Aegis's chosen port; not conflicting with Splunk's `:8089/services/mcp`). Document this in the troubleshooting section and as a JSON comment in the example file (JSON-with-comments is unsupported, so put the port-collision note in the surrounding markdown, not inside the JSON file).
- **`docs/integrations/README.md` includes a tool-equivalence table** mapping each MCP tool to the matching Surface 1 middleware function — so a developer who reads the index sees "MCP `aegis_score_prompt_injection` == middleware `aegis_mw.model_middleware.pre_inference_scan`". This is the cross-surface conceptual map.
- This story has NO Python files. Markdown + JSON only. Verification confirms via `find docs/integrations -name '*.py'` returning empty.

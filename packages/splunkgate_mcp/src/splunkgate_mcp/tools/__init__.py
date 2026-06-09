"""SplunkGate MCP tool modules.

Each module here owns one MCP tool exposed by the SplunkGate MCP server
(Surface 2). Tool modules MUST expose a `register(server)` helper that
calls `splunkgate_mcp.server.register_tool(...)` so bootstrap can wire
them in idempotently.
"""

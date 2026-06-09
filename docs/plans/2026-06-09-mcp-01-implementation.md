# story-mcp-01 — MCP server skeleton implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `splunkgate_mcp` package as a working MCP server skeleton on the official `mcp` Python SDK (1.27.2 installed), with stdio + Streamable HTTP transports, a `register_tool` helper that downstream tool-stories plug into, OTel span attribute builder, and a `_ping` health-check tool. Acceptance: ≥10 BDD tests pass + 5 shell-verification commands all return OK.

**Architecture:** FastMCP server from `mcp.server.fastmcp` is the SDK boundary. We wrap it with our own `register_tool(name, fn, input_schema, output_schema, description)` registry helper that (a) calls `FastMCP.add_tool` for protocol exposure AND (b) stores a `RegisteredTool` dataclass in our internal `_REGISTERED_TOOLS: dict[str, RegisteredTool]` for test inspection. Transport choice resolves from `SPLUNKGATE_MCP_TRANSPORT` env var (`stdio` default, `http` opt-in); HTTP transport binds 127.0.0.1 + validates Origin header (MCP spec DNS-rebinding mitigation). OTel attribute builder co-emits `mcp.method.name`/`mcp.session.id`/`mcp.protocol.version` per OTel GenAI semconv. All tools register at server bootstrap.

**Tech Stack:** Python 3.13, `mcp[cli]` 1.27.2, `pydantic` 2.x, `opentelemetry-api`/`-sdk`, `splunkgate-core` workspace dep (Verdict + ConfigError), `structlog`, pytest + hypothesis for tests.

**Quality bar:** Same as PR #113 — live verification + full pr-review-toolkit fleet (code/security/simplification reviewers in parallel) + zero `--no-verify`. Pre-commit hooks (ruff, ruff-format, mypy --strict for core+judges, 400-LOC cap, no-print, no-secrets) all pass.

**6 revisions from design doc** (`docs/plans/2026-06-09-mcp-design.md`) referenced where they apply — most are for mcp-05; this story has none beyond the existing spec.

---

## File structure

| File | Purpose | LOC budget |
|---|---|---|
| `packages/splunkgate_mcp/pyproject.toml` | Workspace member; declares deps on `mcp[cli]`, `pydantic`, `opentelemetry-*`, `splunkgate-core`, `splunkgate-judges`, `structlog`. UPDATE existing file. | ≤ 50 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py` | `__version__ = "0.1.0"`. UPDATE existing file (currently 0.0.1). | ≤ 5 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py` | Exports `VERDICT_OUTPUT_SCHEMA = Verdict.model_json_schema()`. NEW. | ≤ 30 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/otel.py` | `build_span_attributes(session_id, method_name)` → dict. NEW. | ≤ 60 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/server.py` | FastMCP instance, `register_tool` helper, `_REGISTERED_TOOLS` dict, `resolve_transport`, `serve_stdio`, `serve_http`, `_ping` tool, Origin-header middleware for HTTP. NEW. | ≤ 400 (cap) |
| `packages/splunkgate_mcp/src/splunkgate_mcp/_test_helpers.py` | `list_tools_for_test()` reads `_REGISTERED_TOOLS`. NEW. | ≤ 30 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py` | `python -m splunkgate_mcp` entrypoint. NEW. | ≤ 30 |
| `packages/splunkgate_mcp/src/splunkgate_mcp/py.typed` | Marker file (PEP 561). NEW. EXISTS already — keep. | 0 |
| `packages/splunkgate_mcp/tests/__init__.py` | Empty. EXISTS — keep. | 0 |
| `packages/splunkgate_mcp/tests/test_server_skeleton.py` | ≥10 BDD tests per spec. REPLACES existing `test_smoke.py`. | ≤ 400 |

The existing `tests/test_smoke.py` becomes obsolete — its single test (`test_version_present`) is folded into `test_server_skeleton.py`.

---

## Pre-flight: branch + sprint-status flip

### Task 0: Branch + sprint-status flip on mcp-01

**Files:**
- Modify: `docs/sprint-status.yaml` (flip story-mcp-01 PENDING → IN_PROGRESS)

- [ ] **Step 1: Confirm we're on `main` and clean**

```bash
cd /Users/abu/dev/hackathon/splunk/workspace/aegis
git checkout main && git pull --ff-only
git status --short  # must be empty
```

- [ ] **Step 2: Create branch**

```bash
git checkout -b feat/story-mcp-01
```

- [ ] **Step 3: Flip story-mcp-01 to IN_PROGRESS in sprint-status.yaml**

Open `docs/sprint-status.yaml`, find the `story-mcp-01-server-skeleton-with-mcp-python-sdk` entry, change `status: PENDING` to `status: IN_PROGRESS`.

- [ ] **Step 4: Commit**

```bash
git add docs/sprint-status.yaml
git commit -m "chore(sprint-status): mcp-01 PENDING → IN_PROGRESS"
```

---

## Task 1: Update package deps + version bump

**Files:**
- Modify: `packages/splunkgate_mcp/pyproject.toml`
- Modify: `packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py`

- [ ] **Step 1: Write the failing test (test must run from package root)**

Replace `packages/splunkgate_mcp/tests/test_smoke.py` with `packages/splunkgate_mcp/tests/test_server_skeleton.py`. First test asserts version is 0.1.0:

```python
"""Behavioral tests for story-mcp-01: SplunkGate MCP server skeleton."""

from __future__ import annotations

import splunkgate_mcp


def test_version_is_0_1_0() -> None:
    """Package version bumped from 0.0.1 stub to 0.1.0 first-real-skeleton."""
    assert splunkgate_mcp.__version__ == "0.1.0"
```

Delete `packages/splunkgate_mcp/tests/test_smoke.py`.

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_version_is_0_1_0 -v
```

Expected: FAIL with `AssertionError: assert '0.0.1' == '0.1.0'`

- [ ] **Step 3: Bump version**

Replace contents of `packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py` with:

```python
"""SplunkGate MCP server (Surface 2)."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_version_is_0_1_0 -v
```

Expected: PASS.

- [ ] **Step 5: Update pyproject.toml dependencies**

Replace `packages/splunkgate_mcp/pyproject.toml` with:

```toml
[project]
name = "splunkgate-mcp"
version = "0.1.0"
description = "SplunkGate MCP server (Surface 2) — runtime AI agent safety net exposed to any MCP client"
requires-python = ">=3.13"
license = { text = "Apache-2.0" }
dependencies = [
    "splunkgate-core",
    "splunkgate-judges",
    "mcp[cli]>=1.27.0",
    "pydantic>=2.10",
    "opentelemetry-api>=1.27",
    "opentelemetry-sdk>=1.27",
    "structlog>=24.4",
]

[tool.uv.sources]
splunkgate-core = { workspace = true }
splunkgate-judges = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/splunkgate_mcp"]
```

- [ ] **Step 6: Re-sync workspace + verify deps install**

```bash
uv sync
uv run python -c "from mcp.server.fastmcp import FastMCP; print('FastMCP OK')"
```

Expected: prints `FastMCP OK`.

- [ ] **Step 7: Commit**

```bash
git add packages/splunkgate_mcp/pyproject.toml \
        packages/splunkgate_mcp/src/splunkgate_mcp/__init__.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git rm packages/splunkgate_mcp/tests/test_smoke.py
git commit -m "feat(mcp): bump version 0.0.1→0.1.0 + add real deps"
```

---

## Task 2: `schemas.py` — Verdict outputSchema export

**Files:**
- Create: `packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing test**

Append to `test_server_skeleton.py`:

```python
def test_verdict_output_schema_matches_pydantic() -> None:
    """schemas.VERDICT_OUTPUT_SCHEMA must equal Verdict.model_json_schema()."""
    from splunkgate_core.verdict import Verdict

    from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA

    assert VERDICT_OUTPUT_SCHEMA == Verdict.model_json_schema()
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_verdict_output_schema_matches_pydantic -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'splunkgate_mcp.schemas'`.

- [ ] **Step 3: Create schemas.py**

```python
"""Output schemas exposed by the SplunkGate MCP server's tools.

Per docs/plans/2026-06-09-mcp-design.md § Architecture, every tool's
`outputSchema` is derived from a Pydantic model via `model_json_schema()`
so MCP protocol-level validation catches schema drift at the server
boundary.

This module exposes only the Verdict schema. The AuditReport schema
(for story-mcp-05's `splunkgate_audit_trace`) joins in a later PR.
"""

from __future__ import annotations

from typing import Any

from splunkgate_core.verdict import Verdict

VERDICT_OUTPUT_SCHEMA: dict[str, Any] = Verdict.model_json_schema()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_verdict_output_schema_matches_pydantic -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): schemas.py — VERDICT_OUTPUT_SCHEMA export"
```

---

## Task 3: `otel.py` — span attribute builder

**Files:**
- Create: `packages/splunkgate_mcp/src/splunkgate_mcp/otel.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_server_skeleton.py`:

```python
def test_otel_span_attributes_contains_required_keys() -> None:
    """build_span_attributes returns dict with the 3 required keys."""
    from splunkgate_mcp.otel import build_span_attributes

    attrs = build_span_attributes(session_id="abc123", method_name="tools/call")

    assert attrs["mcp.method.name"] == "tools/call"
    assert attrs["mcp.session.id"] == "abc123"
    assert attrs["mcp.protocol.version"] == "2025-11-25"


def test_otel_span_attributes_protocol_version_is_2025_11_25() -> None:
    """MCP protocol version is the Stable 2025-11-25 (NOT 2025-03-26)."""
    from splunkgate_mcp.otel import MCP_PROTOCOL_VERSION

    assert MCP_PROTOCOL_VERSION == "2025-11-25"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k otel -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create otel.py**

```python
"""OTel attribute builder for SplunkGate MCP server spans.

Per context/10-standards/02-otel-genai-semantic-conventions.md, MCP
sub-convention attributes (`mcp.method.name`, `mcp.session.id`,
`mcp.protocol.version`) co-emit with the `gen_ai.evaluation.result`
event that `splunkgate_core.otel` produces. This module exposes the
attribute builder; the actual evaluation event emission stays in
splunkgate_core (we reuse, do not duplicate).
"""

from __future__ import annotations

from typing import Any

# MCP spec version per context/10-standards/01-mcp-spec-deep.md (Stable).
# Do NOT hardcode "2025-03-26" — that's Splunk's older version per the
# CiscoDevNet README.
MCP_PROTOCOL_VERSION = "2025-11-25"


def build_span_attributes(
    *, session_id: str, method_name: str
) -> dict[str, Any]:
    """Build the dict of MCP sub-convention attributes for a tool-call span.

    The caller wraps each tool invocation in a SERVER-kind span named
    `{method_name} {tool_name}` per the OTel GenAI semconv guidance and
    sets these attributes on it.
    """
    return {
        "mcp.method.name": method_name,
        "mcp.session.id": session_id,
        "mcp.protocol.version": MCP_PROTOCOL_VERSION,
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k otel -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/otel.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): otel.py — build_span_attributes helper"
```

---

## Task 4: `server.py` skeleton — `RegisteredTool` + `_REGISTERED_TOOLS` + `register_tool`

**Files:**
- Create: `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_server_skeleton.py`:

```python
def test_server_module_imports_official_mcp_sdk() -> None:
    """The `server` instance is from the official `mcp` SDK, not a fork."""
    from splunkgate_mcp.server import server

    assert type(server).__module__.startswith("mcp.")


def test_register_tool_adds_to_internal_registry() -> None:
    """register_tool populates _REGISTERED_TOOLS with a RegisteredTool entry."""
    from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
    from splunkgate_mcp.server import _REGISTERED_TOOLS, register_tool

    # Clean slate for the test (test runs in isolation per pytest fixture)
    _REGISTERED_TOOLS.clear()

    async def noop_fn(args: dict[str, object]) -> dict[str, object]:
        return {"verdict": "ALLOW"}

    register_tool(
        name="_test_tool",
        fn=noop_fn,
        input_schema={"type": "object"},
        output_schema=VERDICT_OUTPUT_SCHEMA,
        description="Test tool",
    )

    assert "_test_tool" in _REGISTERED_TOOLS
    entry = _REGISTERED_TOOLS["_test_tool"]
    assert entry.name == "_test_tool"
    assert entry.outputSchema == VERDICT_OUTPUT_SCHEMA
    assert entry.input_schema == {"type": "object"}
    assert callable(entry.fn)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k "imports_official_mcp or register_tool_adds" -v
```

Expected: FAIL.

- [ ] **Step 3: Create initial `server.py`**

```python
"""SplunkGate MCP server bootstrap on the official `mcp` Python SDK.

Per docs/architecture.md ADR-004 + ADR-004a, SplunkGate runs its OWN
MCP server alongside Splunk MCP Server (Splunkbase app 7931) and SAIA
(app 7245). The three prefixes (`splunk_*`, `saia_*`, `splunkgate_*`)
partition cleanly in any multi-server MCP client config.

This module owns:
- The `FastMCP` server instance (the SDK boundary)
- A `register_tool(name, fn, input_schema, output_schema, description)`
  helper that (a) wires the tool into the FastMCP protocol surface AND
  (b) records it in our internal `_REGISTERED_TOOLS` dict
- `_REGISTERED_TOOLS: dict[str, RegisteredTool]` — the registry that
  tests enumerate via `splunkgate_mcp._test_helpers.list_tools_for_test`
  (FastMCP's async protocol surface is not a sync registry)
- `resolve_transport()` — chooses between stdio/http based on env var
- `serve_stdio()` / `serve_http()` — the two entry points

Tool registration happens at module import time so `tools/list` works
immediately when the server boots. The `_ping` no-op tool is registered
unconditionally for skeleton-level tests + Splunk-app dashboard heartbeat.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA

# FastMCP instance — the SDK boundary. Name is the canonical server name
# advertised over the MCP protocol's `initialize` handshake.
server: FastMCP = FastMCP("splunkgate-mcp")


# A tool function: takes a kwargs dict, returns a dict the SDK serializes
# to MCP `structuredContent`. Async because AI Defense + Splunk REST calls
# are async; the type matches the FastMCP tool signature.
ToolFn = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Source-of-truth record for a registered MCP tool.

    Stored in `_REGISTERED_TOOLS` at registration time. Tests enumerate
    these via `_test_helpers.list_tools_for_test()` because FastMCP's
    `list_tools()` is exposed via the MCP protocol's async `tools/list`
    method, not as a sync registry call.

    Attribute name `outputSchema` (camelCase) deliberately mirrors the
    MCP wire-protocol field name — tests assert against it via the same
    spelling MCP clients see.
    """

    name: str
    fn: ToolFn
    input_schema: dict[str, Any]
    outputSchema: dict[str, Any]
    description: str


# The registry. Tests read this via _test_helpers; production reads via
# FastMCP's tool-call protocol surface (which we wire below in register_tool).
_REGISTERED_TOOLS: dict[str, RegisteredTool] = {}


def register_tool(
    *,
    name: str,
    fn: ToolFn,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    description: str,
) -> None:
    """Register a tool with both FastMCP (protocol) and our registry (tests).

    Downstream stories (mcp-02 through mcp-05) call this from their tool
    modules. Signature is locked per docs/stories/story-mcp-01-*.md notes.
    """
    _REGISTERED_TOOLS[name] = RegisteredTool(
        name=name,
        fn=fn,
        input_schema=input_schema,
        outputSchema=output_schema,
        description=description,
    )
    server.add_tool(
        fn=fn,  # type: ignore[arg-type]
        name=name,
        description=description,
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k "imports_official_mcp or register_tool_adds" -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): server.py skeleton + register_tool registry"
```

---

## Task 5: `_test_helpers.list_tools_for_test`

**Files:**
- Create: `packages/splunkgate_mcp/src/splunkgate_mcp/_test_helpers.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing test**

Append to `test_server_skeleton.py`:

```python
def test_list_tools_for_test_returns_registered_tools() -> None:
    """_test_helpers exposes the internal registry without async FastMCP surface."""
    from splunkgate_mcp._test_helpers import list_tools_for_test
    from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
    from splunkgate_mcp.server import _REGISTERED_TOOLS, register_tool

    _REGISTERED_TOOLS.clear()

    async def noop_fn(args: dict[str, object]) -> dict[str, object]:
        return {"verdict": "ALLOW"}

    register_tool(
        name="_helper_test",
        fn=noop_fn,
        input_schema={"type": "object"},
        output_schema=VERDICT_OUTPUT_SCHEMA,
        description="x",
    )

    tools = list_tools_for_test()
    names = [t.name for t in tools]
    assert "_helper_test" in names
    target = next(t for t in tools if t.name == "_helper_test")
    assert target.outputSchema == VERDICT_OUTPUT_SCHEMA
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_list_tools_for_test_returns_registered_tools -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `_test_helpers.py`**

```python
"""Test-only helpers that bypass FastMCP's async protocol surface.

FastMCP exposes registered tools via the MCP protocol's async `tools/list`
method (returning over JSON-RPC). For unit tests we want sync inspection
of the registry without spinning up the protocol harness. The internal
`_REGISTERED_TOOLS` dict in `server.py` is the canonical source — this
module exposes it as a list under a test-only name.

This module's name starts with an underscore so it's never accidentally
imported from production code; downstream tool stories (mcp-02 through
mcp-05) import it only inside their `tests/` modules.
"""

from __future__ import annotations

from splunkgate_mcp.server import _REGISTERED_TOOLS, RegisteredTool


def list_tools_for_test() -> list[RegisteredTool]:
    """Return the values of the internal `_REGISTERED_TOOLS` registry."""
    return list(_REGISTERED_TOOLS.values())
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_list_tools_for_test_returns_registered_tools -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/_test_helpers.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): _test_helpers.list_tools_for_test"
```

---

## Task 6: `_ping` tool registration at bootstrap

**Files:**
- Modify: `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing test**

Append to `test_server_skeleton.py`:

```python
def test_ping_tool_registered_at_bootstrap() -> None:
    """The `_ping` no-op tool is registered the moment server.py is imported."""
    # Re-import to trigger bootstrap (the test above clears the registry)
    from splunkgate_mcp.server import _REGISTERED_TOOLS, ensure_ping_registered

    ensure_ping_registered()

    assert "_ping" in _REGISTERED_TOOLS
    ping = _REGISTERED_TOOLS["_ping"]
    # _ping's outputSchema is the Verdict schema per spec
    from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA
    assert ping.outputSchema == VERDICT_OUTPUT_SCHEMA
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_ping_tool_registered_at_bootstrap -v
```

Expected: FAIL (`ImportError` on `ensure_ping_registered`).

- [ ] **Step 3: Append `_ping` + `ensure_ping_registered` to `server.py`**

Append to `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`:

```python
# --- _ping no-op tool ---------------------------------------------------
#
# The cheapest health-probe surface. Returns a static ALLOW Verdict so
# the Splunk app's dashboard heartbeat panel can poll without needing
# valid input or live judges. Stays registered after stories mcp-02..05
# land — it's the canonical "is the server up?" check.

from datetime import UTC, datetime
from uuid import uuid4

from splunkgate_core.verdict import Severity, Verdict, VerdictLabel


async def _ping(args: dict[str, object]) -> dict[str, object]:
    """No-op health check. Returns a static ALLOW verdict.

    Args are ignored — the tool exists only to verify protocol round-trip.
    The verdict is structurally valid (passes Verdict pydantic) so dashboards
    rendering recent verdicts don't blow up on parsing.
    """
    verdict = Verdict(
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        verdict=VerdictLabel.ALLOW,
        severity=Severity.NONE_SEVERITY,
        rules=[],
        explanation="health check (no-op)",
        surface="mcp_score",  # _ping uses mcp_score since it's the default scoring surface
        latency_ms=0.0,
    )
    return verdict.model_dump(mode="json")


_PING_REGISTERED = False


def ensure_ping_registered() -> None:
    """Idempotent _ping registration. Called at module import + by tests."""
    global _PING_REGISTERED
    if _PING_REGISTERED:
        return
    register_tool(
        name="_ping",
        fn=_ping,
        input_schema={"type": "object", "properties": {}, "additionalProperties": True},
        output_schema=VERDICT_OUTPUT_SCHEMA,
        description="Health-probe no-op. Returns a static ALLOW verdict.",
    )
    _PING_REGISTERED = True


# Register _ping at import time so `tools/list` works immediately.
ensure_ping_registered()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py::test_ping_tool_registered_at_bootstrap -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): _ping no-op tool registered at bootstrap"
```

---

## Task 7: `resolve_transport()` — env-driven transport choice

**Files:**
- Modify: `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_server_skeleton.py`:

```python
def test_resolve_transport_defaults_to_stdio(monkeypatch) -> None:
    """SPLUNKGATE_MCP_TRANSPORT unset → stdio."""
    from splunkgate_mcp.server import resolve_transport

    monkeypatch.delenv("SPLUNKGATE_MCP_TRANSPORT", raising=False)
    assert resolve_transport() == "stdio"


def test_resolve_transport_http_when_env_set(monkeypatch) -> None:
    """SPLUNKGATE_MCP_TRANSPORT=http → http."""
    from splunkgate_mcp.server import resolve_transport

    monkeypatch.setenv("SPLUNKGATE_MCP_TRANSPORT", "http")
    assert resolve_transport() == "http"


def test_resolve_transport_invalid_raises(monkeypatch) -> None:
    """Invalid SPLUNKGATE_MCP_TRANSPORT raises ConfigError."""
    from splunkgate_core.errors import ConfigError

    from splunkgate_mcp.server import resolve_transport

    monkeypatch.setenv("SPLUNKGATE_MCP_TRANSPORT", "ftp")
    with pytest.raises(ConfigError, match="SPLUNKGATE_MCP_TRANSPORT"):
        resolve_transport()
```

And add `import pytest` at the top of the test file if not already present.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k resolve_transport -v
```

Expected: FAIL (`ImportError`).

- [ ] **Step 3: Append `resolve_transport` to `server.py`**

Append to `server.py`:

```python
# --- Transport resolution -----------------------------------------------
#
# Per the MCP spec, clients SHOULD support stdio whenever possible.
# stdio is therefore our default. Streamable HTTP is opt-in via the
# `SPLUNKGATE_MCP_TRANSPORT` env var; it binds 127.0.0.1 only and
# validates the Origin header per the spec's DNS-rebinding mitigation
# (see `_check_origin` further down in this file).

from typing import Literal

from splunkgate_core.errors import ConfigError

Transport = Literal["stdio", "http"]


def resolve_transport() -> Transport:
    """Read SPLUNKGATE_MCP_TRANSPORT; default to stdio.

    Raises ConfigError on unknown values so misconfiguration surfaces
    at startup, not during the first protocol message.
    """
    raw = os.environ.get("SPLUNKGATE_MCP_TRANSPORT", "stdio").lower()
    if raw == "stdio":
        return "stdio"
    if raw == "http":
        return "http"
    raise ConfigError(
        f"SPLUNKGATE_MCP_TRANSPORT must be 'stdio' or 'http', got {raw!r}"
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k resolve_transport -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): resolve_transport — env-driven stdio/http choice"
```

---

## Task 8: `serve_stdio()` + `serve_http()` entry points

**Files:**
- Modify: `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_server_skeleton.py`:

```python
def test_serve_stdio_is_async_callable() -> None:
    """serve_stdio is an async function that wraps FastMCP.run_stdio_async."""
    import inspect

    from splunkgate_mcp.server import serve_stdio

    assert inspect.iscoroutinefunction(serve_stdio)


def test_serve_http_binds_127_0_0_1() -> None:
    """serve_http defaults to 127.0.0.1 binding (not 0.0.0.0)."""
    from splunkgate_mcp.server import HTTP_BIND_HOST, HTTP_BIND_PORT

    assert HTTP_BIND_HOST == "127.0.0.1"
    assert HTTP_BIND_PORT == 8765  # per design doc
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k "serve_stdio_is_async or serve_http_binds" -v
```

Expected: FAIL.

- [ ] **Step 3: Append entry points to `server.py`**

Append to `server.py`:

```python
# --- Entry points -------------------------------------------------------
#
# HTTP_BIND_HOST is locked to 127.0.0.1 per the MCP spec's DNS-rebinding
# mitigation guidance. HTTP_BIND_PORT is the SplunkGate-chosen port; it
# does NOT conflict with Splunk's MCP Server (which serves at
# :8089/services/mcp under their REST surface).

HTTP_BIND_HOST = "127.0.0.1"
HTTP_BIND_PORT = 8765


async def serve_stdio() -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects."""
    await server.run_stdio_async()


async def serve_http() -> None:
    """Run the MCP server over Streamable HTTP bound to 127.0.0.1."""
    # FastMCP exposes the host/port via the `settings` attribute.
    server.settings.host = HTTP_BIND_HOST
    server.settings.port = HTTP_BIND_PORT
    await server.run_streamable_http_async()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k "serve_stdio_is_async or serve_http_binds" -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): serve_stdio + serve_http (127.0.0.1 + 8765)"
```

---

## Task 9: Origin-header validation middleware

**Files:**
- Modify: `packages/splunkgate_mcp/src/splunkgate_mcp/server.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

This task implements the BDD acceptance criterion: HTTP POST with cross-origin `Origin` header returns 403.

- [ ] **Step 1: Write the failing test**

Append to `test_server_skeleton.py`:

```python
import asyncio

from starlette.applications import Starlette
from starlette.testclient import TestClient


def test_http_origin_header_rejects_cross_origin() -> None:
    """HTTP POST with `Origin: https://attacker.example` returns 403."""
    from splunkgate_mcp.server import build_http_app

    app: Starlette = build_http_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        headers={"Origin": "https://attacker.example"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 403


def test_http_origin_header_accepts_localhost() -> None:
    """HTTP POST with `Origin: http://127.0.0.1:*` passes the check."""
    from splunkgate_mcp.server import build_http_app

    app: Starlette = build_http_app()
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        headers={"Origin": "http://127.0.0.1:3000"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    # Origin check passed → status is NOT 403 (may be 200 or 500 if the
    # MCP handshake didn't init, but Origin was accepted)
    assert resp.status_code != 403
```

Note: `starlette` is pulled in transitively via `mcp[cli]` (mcp depends on starlette). No new dep needed.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k http_origin -v
```

Expected: FAIL (`ImportError`).

- [ ] **Step 3: Append Origin-check middleware + `build_http_app` to `server.py`**

Append to `server.py`:

```python
# --- HTTP Origin validation (MCP DNS-rebinding mitigation) --------------
#
# Per context/10-standards/01-mcp-spec-deep.md: "The HTTP transport MUST
# validate the Origin header." Allowed origins are localhost variants —
# everything else is 403.

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ALLOWED_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _is_allowed_origin(origin_header: str | None) -> bool:
    """Return True if the Origin header is missing or points at localhost.

    Missing Origin is allowed because legitimate MCP clients (Claude Desktop,
    Cursor) running over the stdio bridge may not set it. Any non-localhost
    origin is rejected per MCP DNS-rebinding mitigation.
    """
    if origin_header is None:
        return True
    # Origin is `scheme://host[:port]` per RFC 6454
    try:
        # cheap parse: drop scheme, drop port
        without_scheme = origin_header.split("://", 1)[1]
        host = without_scheme.split(":", 1)[0]
    except IndexError:
        return False
    return host in _ALLOWED_ORIGIN_HOSTS


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin POSTs with HTTP 403."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        origin = request.headers.get("origin")
        if not _is_allowed_origin(origin):
            return Response(status_code=403, content=b"Origin not allowed")
        return await call_next(request)


def build_http_app() -> Starlette:
    """Build the Starlette ASGI app with the Origin-check middleware applied.

    Extracted as its own function so tests can exercise the middleware
    without spinning up a real uvicorn worker.
    """
    app: Starlette = server.streamable_http_app()
    app.add_middleware(OriginCheckMiddleware)
    return app
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k http_origin -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Update `serve_http()` to use `build_http_app`**

In `server.py`, REPLACE the existing `serve_http` function with:

```python
async def serve_http() -> None:
    """Run the MCP server over Streamable HTTP bound to 127.0.0.1.

    Uses `build_http_app` so the Origin-check middleware is applied to
    every request. Runs uvicorn directly (rather than FastMCP's helper)
    because we want control over the ASGI app stack.
    """
    import uvicorn

    app = build_http_app()
    config = uvicorn.Config(
        app,
        host=HTTP_BIND_HOST,
        port=HTTP_BIND_PORT,
        log_level="info",
    )
    await uvicorn.Server(config).serve()
```

- [ ] **Step 6: Run all server tests to ensure no regression**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): Origin-header validation middleware for HTTP transport"
```

---

## Task 10: `__main__.py` entry point

**Files:**
- Create: `packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py`
- Modify: `packages/splunkgate_mcp/tests/test_server_skeleton.py`

- [ ] **Step 1: Write the failing test**

Append to `test_server_skeleton.py`:

```python
def test_main_module_chooses_transport_from_env(monkeypatch) -> None:
    """`python -m splunkgate_mcp` dispatches based on resolve_transport()."""
    import subprocess
    import sys

    # Smoke: import the module and verify it has `main` and `entrypoint`
    from splunkgate_mcp import __main__ as m

    assert hasattr(m, "main")
    assert callable(m.main)


def test_main_module_runnable_via_subprocess() -> None:
    """`uv run python -m splunkgate_mcp --version` exits 0."""
    import subprocess
    import sys

    # Use a --version flag rather than actually running the server.
    # Run with a 3-sec timeout in case --version isn't handled.
    result = subprocess.run(
        [sys.executable, "-m", "splunkgate_mcp", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k main_module -v
```

Expected: FAIL.

- [ ] **Step 3: Create `__main__.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -k main_module -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py \
        packages/splunkgate_mcp/tests/test_server_skeleton.py
git commit -m "feat(mcp): __main__.py — python -m splunkgate_mcp entrypoint"
```

---

## Task 11: Full BDD acceptance suite + spec shell verification

This task runs the spec's full verification script and confirms ≥10 tests pass + every shell command returns OK.

- [ ] **Step 1: Run the full test suite for this package**

```bash
uv run pytest packages/splunkgate_mcp/tests/test_server_skeleton.py -v 2>&1 | tee /tmp/mcp01-tests.log
```

Expected: ≥10 PASSED, 0 FAILED.

Count: `grep -cE "PASSED" /tmp/mcp01-tests.log` must output `>= 10`.

- [ ] **Step 2: Run spec shell verification (lifted verbatim from story-mcp-01.md)**

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
```
Expected: `OK`

```bash
# Test helper exposes the registry without going through the FastMCP async protocol surface
uv run python -c "
from splunkgate_mcp._test_helpers import list_tools_for_test
tools = list_tools_for_test()
assert any(t.name == '_ping' for t in tools), [t.name for t in tools]
print('OK')
"
```
Expected: `OK`

```bash
# mcp SDK is the official one
uv run python -c "import mcp, mcp.server; print('official mcp:', mcp.__name__)"
```
Expected: `official mcp: mcp`

```bash
# OTel attribute presence smoke
uv run python -c "
from splunkgate_mcp.otel import build_span_attributes
attrs = build_span_attributes(session_id='abc123', method_name='tools/call')
assert attrs['mcp.method.name'] == 'tools/call'
assert attrs['mcp.session.id'] == 'abc123'
assert attrs['mcp.protocol.version'] == '2025-11-25'
print('OK')
"
```
Expected: `OK`

```bash
# 400-LOC cap on every new source file
for f in packages/splunkgate_mcp/src/splunkgate_mcp/server.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/schemas.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/otel.py \
         packages/splunkgate_mcp/src/splunkgate_mcp/__main__.py; do
  wc -l "$f" | awk '{ if ($1 > 400) { print "OVERFLOW " $0; exit 1 } }'
done
```
Expected: no output (no overflow).

```bash
# §14 clean on production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/splunkgate_mcp/src/
```
Expected: no output.

- [ ] **Step 3: Subprocess smoke — server boots cleanly via `python -m splunkgate_mcp --version`**

```bash
uv run python -m splunkgate_mcp --version
```

Expected: `splunkgate-mcp 0.1.0` (or similar).

- [ ] **Step 4: Pre-commit hooks**

```bash
uv run pre-commit run --all-files
```

Expected: all hooks PASS (ruff, ruff-format, mypy --strict on splunkgate_core+judges, 400-LOC cap, no-print, no-secrets).

If any hook fails, fix the underlying issue and re-run. **DO NOT use `--no-verify`** per `memory:feedback_deadline_no_excuse_mediocre`.

- [ ] **Step 5: Commit any final cleanup if needed**

```bash
git status --short
# If clean, skip this commit. If anything pending, commit before PR.
git diff
git add -A
git commit -m "chore(mcp): cleanup pass before PR open"
```

---

## Task 12: Open PR + dispatch review fleet

**Files:** none (process step)

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/story-mcp-01
```

- [ ] **Step 2: Open PR via `gh`**

```bash
gh pr create --base main --head feat/story-mcp-01 \
  --title "feat(mcp): story-mcp-01 — server skeleton + register_tool + _ping" \
  --body "$(cat <<'EOF'
## Summary
- `splunkgate_mcp` package leaves stub state — full server skeleton on official `mcp` 1.27.2 SDK
- Exposes `register_tool(name, fn, input_schema, output_schema, description)` registry helper for stories mcp-02 through mcp-05 to plug into
- `_REGISTERED_TOOLS: dict[str, RegisteredTool]` is source of truth; `_test_helpers.list_tools_for_test()` is the canonical test enumeration (FastMCP async surface is not a sync registry)
- Transports: stdio (default per MCP spec) + Streamable HTTP env-toggled (\`SPLUNKGATE_MCP_TRANSPORT=http\`); HTTP binds 127.0.0.1 + Origin header validation per MCP DNS-rebinding mitigation
- OTel attribute builder co-emits `mcp.method.name`/`mcp.session.id`/`mcp.protocol.version=2025-11-25` per OTel GenAI semconv
- `_ping` no-op health-probe tool registered at bootstrap — Splunk app dashboard heartbeat consumer
- `python -m splunkgate_mcp` + `--version` flag for liveness check

## Story
docs/stories/story-mcp-01-server-skeleton-with-mcp-python-sdk.md

## Design
docs/plans/2026-06-09-mcp-design.md (Phase A0 design doc, PR #114)

## Test plan
- [x] Spec BDD acceptance — ≥10 tests pass
- [x] Spec shell verification — all 6 commands return OK / no output
- [x] 400-LOC cap on every new source file
- [x] §14 grep clean on production code
- [x] Pre-commit hooks pass (ruff / ruff-format / mypy --strict / no-print / no-secrets)
- [x] `python -m splunkgate_mcp --version` boots cleanly
- [ ] Review fleet (code-reviewer + simplification-reviewer + security-reviewer) signs off

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Dispatch review fleet (parallel)**

Per CLAUDE.md step 7 + `memory:feedback_use_full_pr_review_toolkit`, dispatch 3 reviewers concurrently using the `Agent` tool. Each gets a focused prompt scoped to this PR's diff:

- `code-reviewer`: focus on register_tool API stability for stories mcp-02..05, RegisteredTool dataclass shape, FastMCP integration correctness
- `simplification-reviewer`: check for over-engineering (Origin allowlist parser, dataclass vs Pydantic, etc.)
- `security-reviewer`: Origin header parsing correctness, 127.0.0.1 binding, no info leak on 403, no env-var-in-error-message leaks

- [ ] **Step 4: Address review findings**

For each review finding:
1. If it's a real bug or actionable improvement, commit a fix on the same branch with a message citing the reviewer
2. If it's a disagreement, post a PR comment explaining why with rationale grounded in the spec / design doc
3. Per `memory:feedback_pr_review_every_pr`, the review fleet is the quality gate — don't merge with unaddressed substantive findings

- [ ] **Step 5: Live-verify the server boots end-to-end before merge**

```bash
# Background-start the HTTP server and probe it
SPLUNKGATE_MCP_TRANSPORT=http uv run python -m splunkgate_mcp &
SERVER_PID=$!
sleep 2
# Hit the / endpoint to verify boot
curl -s -o /dev/null -w "%{http_code}\n" \
     -H "Origin: http://127.0.0.1:3000" \
     -X POST http://127.0.0.1:8765/mcp \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# Expected: 200 or some 4xx that's NOT 403 (Origin accepted)

# Cross-origin probe MUST return 403
curl -s -o /dev/null -w "%{http_code}\n" \
     -H "Origin: https://attacker.example" \
     -X POST http://127.0.0.1:8765/mcp \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# Expected: 403

kill $SERVER_PID
```

- [ ] **Step 6: Merge PR**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 7: Flip sprint-status to COMPLETE**

```bash
git checkout main && git pull --ff-only
# Edit docs/sprint-status.yaml — change story-mcp-01 from IN_PROGRESS to COMPLETE; add `pr:` and `merged_at:` fields per existing entries' pattern
git add docs/sprint-status.yaml
git commit -m "chore(sprint-status): mcp-01 IN_PROGRESS → COMPLETE"
git push
```

---

## Self-review

After writing this plan, I re-read the story spec and design doc with fresh eyes:

1. **Spec coverage**: All 10 BDD acceptance criteria covered:
   - "imports official mcp SDK" → Task 4, test_server_module_imports_official_mcp_sdk
   - "_ping registered, outputSchema deep-equals" → Task 6
   - "list_tools_for_test returns _ping" → Task 5 + 6
   - "list_tools_for_test entry exposes outputSchema" → Task 5
   - "resolve_transport defaults to stdio" → Task 7
   - "resolve_transport http when env set" → Task 7
   - "OTel attribute presence" → Task 3
   - "HTTP Origin 403" → Task 9
   - "≥10 tests pass" → Task 11 verifies
   - "wc -l server.py ≤ 400" → Task 11 verifies
   - "§14 grep empty" → Task 11 verifies

2. **Placeholder scan**: No "TBD", no "TODO", no "implement later", no "fill in details". Every code block is complete and runnable.

3. **Type consistency check**:
   - `ToolFn` defined in Task 4, used by `_ping` in Task 6 (return type `dict[str, object]` matches both)
   - `RegisteredTool.outputSchema` (camelCase) used consistently across tasks 4, 5, 6, 11
   - `Transport = Literal["stdio", "http"]` defined in Task 7, used by `resolve_transport` and the dispatch in `__main__` (Task 10)
   - `Verdict` imported from `splunkgate_core.verdict`, `ConfigError` from `splunkgate_core.errors` — both exist (verified earlier)

4. **Cross-task references**:
   - Task 5 imports `_REGISTERED_TOOLS` + `RegisteredTool` from `server` (defined Task 4) ✓
   - Task 6 uses `VERDICT_OUTPUT_SCHEMA` from `schemas` (defined Task 2) ✓
   - Task 9's `build_http_app` is called by `serve_http` (Task 8); Task 9 replaces Task 8's stub — explicit replacement instruction included ✓

5. **No stale references**: Story spec mentions `SplunkGateConfigError` but the actual class name is `ConfigError` (verified). Plan uses the correct name throughout.

6. **Quality gates explicit**:
   - Pre-commit hooks (Task 11) — non-negotiable
   - Live-verification (Task 12 Step 5) — same pattern as PR #113
   - Review fleet (Task 12 Step 3) — 3 reviewers in parallel
   - `--no-verify` explicitly banned (cited memory)

Plan is complete and ready to execute.

---

## Execution Handoff

Plan complete and saved to `/Users/abu/dev/hackathon/splunk/workspace/aegis/docs/plans/2026-06-09-mcp-01-implementation.md`.

Two execution options per the writing-plans skill:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task; review between tasks; fastest iteration without context drift; uses `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`; batch execution with checkpoints for review; my full conversation context informs every task.

Given the precision of the story spec + the design doc + the per-task TDD discipline, both approaches will produce the same result. The choice is about your preference for context isolation vs. context continuity.

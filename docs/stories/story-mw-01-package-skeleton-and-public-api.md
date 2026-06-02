# Story — aegis_mw package skeleton and public API

**ID:** story-mw-01-package-skeleton-and-public-api
**Epic:** EPIC-06 — Surface 1 (aegis-mw middleware library for splunklib.ai)
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~1.5h
**Status:** PENDING

---

## User story

**As a** Splunk agent developer who already builds with `splunklib.ai`
**I want to** add Aegis safety to my agent by importing four public classes and passing them as `splunklib.ai.Agent` constructor kwargs
**So that** I get pre-emit interception in three lines of code without learning new framework concepts, and the public API matches the actual `splunklib.ai` middleware contract (4 distinct middleware kwargs) rather than a hallucinated before/after × model/tool shape

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mw/pyproject.toml` — NEW — uv workspace member; deps: `aegis-core`, `aegis-judges`, `splunk-sdk[ai]>=3.0.0`, `pydantic>=2`, `structlog`
- `packages/aegis_mw/src/aegis_mw/__init__.py` — NEW — re-exports the public API: `SafetyToolMiddleware`, `SafetyModelMiddleware`, `SafetySubagentMiddleware`, `SafetyAgentMiddleware`, `Config`, `Profile`, `__version__`
- `packages/aegis_mw/src/aegis_mw/py.typed` — NEW — PEP 561 marker
- `packages/aegis_mw/src/aegis_mw/_base.py` — NEW — shared `_SafetyMiddlewareBase` mixin that holds `config: Config`, `profile: Profile`, `logger: structlog.BoundLogger`, and a `_emit_verdict(verdict)` helper that calls `aegis_core.otel.emit_evaluation_result`; placeholder `SafetyToolMiddleware`, `SafetyModelMiddleware`, `SafetySubagentMiddleware`, `SafetyAgentMiddleware` subclasses each inherit from `splunklib.ai.middleware.AgentMiddleware` and define a stub `*_middleware` method that simply calls `handler(request)` (real logic lands in stories mw-02 through mw-06)
- `packages/aegis_mw/src/aegis_mw/profiles.py` — NEW — stub `Profile` frozen dataclass (`name: str`, `description: str`); single `default` instance only — the full FSI/HIPAA/PubSec profiles land in story-mw-07
- `packages/aegis_mw/src/aegis_mw/config.py` — NEW — `Config` frozen pydantic model: `ai_defense_endpoint`, `ai_defense_api_key: SecretStr | None`, `foundation_sec_enabled: bool = True`, `escalate_on_first_pass_hit: bool = True`, `splunklib_security_first_pass: bool = True`
- `packages/aegis_mw/tests/__init__.py` — NEW — empty
- `packages/aegis_mw/tests/test_public_api.py` — NEW — ≥ 10 behavioral tests covering: each of the 4 middleware classes is importable from `aegis_mw`; each is a subclass of `splunklib.ai.middleware.AgentMiddleware`; passing them as `Agent(tool_middleware=[...], model_middleware=[...], subagent_middleware=[...], agent_middleware=[...])` kwargs accepts the values without TypeError (use a mocked Agent constructor — the real Agent requires Splunk Service); `Profile("default", "...")` constructs; `Config()` constructs with environment defaults
- `packages/aegis_mw/examples/__init__.py` — NEW — empty (the actual `examples/support_agent.py` is built in story-mw-07)

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given packages/aegis_mw/src/aegis_mw/__init__.py exists
When  `uv run python -c "from aegis_mw import SafetyToolMiddleware, SafetyModelMiddleware, SafetySubagentMiddleware, SafetyAgentMiddleware, Config, Profile; print('ok')"` runs
Then  the output is "ok"

Given the 4 middleware classes are defined
When  `uv run python -c "from splunklib.ai.middleware import AgentMiddleware; from aegis_mw import SafetyToolMiddleware, SafetyModelMiddleware, SafetySubagentMiddleware, SafetyAgentMiddleware; print(all(issubclass(c, AgentMiddleware) for c in [SafetyToolMiddleware, SafetyModelMiddleware, SafetySubagentMiddleware, SafetyAgentMiddleware]))"` runs
Then  the output is "True"

Given the public API is locked
When  `uv run python -c "import aegis_mw; print(sorted(n for n in aegis_mw.__all__))"` runs
Then  the output contains exactly: ['Config', 'Profile', 'SafetyAgentMiddleware', 'SafetyModelMiddleware', 'SafetySubagentMiddleware', 'SafetyToolMiddleware']

Given each stub middleware is constructed and used as a splunklib.ai.Agent kwarg shape
When  `uv run pytest packages/aegis_mw/tests/test_public_api.py -v` runs
Then  ≥ 10 tests pass and 0 fail

Given each source file in packages/aegis_mw/src/aegis_mw/
When  `find packages/aegis_mw/src/aegis_mw -name '*.py' -exec wc -l {} +` runs
Then  every file reports ≤ 400 lines

Given the §14 grep is run on changed source (excluding test files)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# Public API imports + 3-line integration shape
uv run python <<'PY'
from splunklib.ai.middleware import AgentMiddleware
from aegis_mw import (
    SafetyToolMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyAgentMiddleware,
    Config,
    Profile,
)

# 1. All 4 are subclasses of the real splunklib.ai middleware base
for cls in [
    SafetyToolMiddleware,
    SafetyModelMiddleware,
    SafetySubagentMiddleware,
    SafetyAgentMiddleware,
]:
    assert issubclass(cls, AgentMiddleware), cls

# 2. The advertised 3-line integration shape constructs without error
tool_mw = [SafetyToolMiddleware(profile="financial_services")]
model_mw = [SafetyModelMiddleware(profile="financial_services")]
# Agent(...) construction itself requires a Splunk Service; we only validate
# that the middleware instances themselves satisfy the AgentMiddleware contract.
assert all(isinstance(m, AgentMiddleware) for m in tool_mw + model_mw)

# 3. Config + Profile both construct
assert Config().splunklib_security_first_pass is True
assert Profile(name="default", description="balanced").name == "default"

print("OK")
PY
# Must print 'OK'

# Tests pass
uv run pytest packages/aegis_mw/tests/test_public_api.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 10

# 400-LOC cap across the package
find packages/aegis_mw/src/aegis_mw -name '*.py' -exec wc -l {} + | awk '$1 > 400 && $2 != "total" { print; exit 1 }'
# Must exit 0

# §14 clean on production code
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/
# Must output nothing

# Lint + typecheck
uv run ruff check packages/aegis_mw/
uv run mypy packages/aegis_mw/src/aegis_mw/
# Both must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, the public splunklib.ai 3.0.0 middleware API is FOUR distinct middleware kwargs on the `Agent` constructor: `tool_middleware`, `subagent_middleware`, `model_middleware`, `agent_middleware`. It is NOT a `before/after × model/tool` matrix.** Any earlier internal notes that described a 2×2 matrix were wrong. The four `*_middleware` wrap-point methods are defined verbatim at `splunklib/ai/middleware.py:104-139`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, the `before_model` / `after_model` / `before_agent` / `after_agent` convenience hooks DO exist at `splunklib/ai/hooks.py:16-95` but are NOT re-exported from `splunklib.ai.__init__`.** Do not depend on them in the public API. If you want to use them internally as sugar, import explicitly: `from splunklib.ai.hooks import before_model`. The four public middleware classes in this story directly subclass `splunklib.ai.middleware.AgentMiddleware`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai 3.0.0 was uploaded to PyPI 2026-05-12T13:57:08.** Pin `splunk-sdk[ai]>=3.0.0` in `pyproject.toml`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai 3.0.0 runs entirely on LangChain v1 (`backend_registry.py:18-24` hard-codes `langchain_backend_factory`).** Transitive — `splunk-sdk[ai]` pulls `langchain>=1.2.18`. Do not add `langchain` directly.
- The 3-line integration shape that this story enables and the README will demonstrate:
  ```python
  from splunklib.ai import Agent
  from aegis_mw import SafetyToolMiddleware, SafetyModelMiddleware
  agent = Agent(
      ...,
      tool_middleware=[SafetyToolMiddleware(profile="financial_services")],
      model_middleware=[SafetyModelMiddleware(profile="financial_services")],
  )
  ```
- This story ships **stubs** for all four middleware classes — each `*_middleware` method just delegates to `await handler(request)`. The real per-class logic lands in stories mw-02 (tool), mw-03/04 (model), mw-05 (subagent), mw-06 (agent). Stub means "subclass, override the right method, no-op pass-through that emits no Verdict yet."
- The `profile=` constructor kwarg in this story only accepts the string `"default"` (stored on the instance). Stories mw-02 through mw-07 thread profile-driven behavior in. Do not raise on other profile names yet — story mw-07 introduces the registry.
- Set `__version__ = "0.1.0"` in `__init__.py`.

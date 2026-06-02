# Story — Profiles + Config (FSI / HIPAA / PubSec / Default) + 30-line support_agent.py demo

**ID:** story-mw-07-profiles-and-config-fsi-hipaa-pubsec
**Epic:** EPIC-06 — Surface 1 (aegis-mw middleware library for splunklib.ai)
**Depends on:** story-mw-02-tool-middleware-with-defenseclaw-args, story-mw-03-model-middleware-pre-inference-scan
**Estimate:** ~2h
**Status:** PENDING

---

## User story

**As a** Splunk agent developer in a regulated industry (financial services, healthcare, public sector)
**I want to** pass a single `profile="financial_services"` (or "healthcare" / "public_sector" / "default") string to every Aegis middleware constructor and have the correct rule chain + emphasis applied uniformly across all 4 middleware layers (tool / model / subagent / agent)
**So that** my agent inherits a vetted compliance profile in one line instead of me curating 11 AI Defense rule names per surface, and the demo video can show the headline 3-line integration on a 30-line example agent

---

## File modification map

Exact files the coding agent creates or modifies for this story:

- `packages/aegis_mw/src/aegis_mw/profiles.py` — UPDATE — replaces the stub `Profile` from story-mw-01 with the full version: `Profile` is a `pydantic.BaseModel` (frozen=True) with fields `name: Literal["default","financial_services","healthcare","public_sector"]`, `description: str`, `rules_pre_inference: tuple[str, ...]`, `rules_post_inference: tuple[str, ...]`, `rules_tool_call: tuple[str, ...]`, `escalate_on_first_pass_hit: bool`, `foundation_sec_enabled: bool`; module-level constants `DEFAULT_PROFILE`, `FINANCIAL_SERVICES_PROFILE`, `HEALTHCARE_PROFILE`, `PUBLIC_SECTOR_PROFILE`; function `resolve_profile(name_or_profile: str | Profile) -> Profile` raising `aegis_core.errors.UnknownProfile` for invalid names
- `packages/aegis_mw/src/aegis_mw/config.py` — UPDATE — `Config` accepts `profile: str | Profile = "default"` and resolves via `resolve_profile`; the four middleware classes read profile-derived fields (rule subsets, foundation_sec_enabled, escalate_on_first_pass_hit) from `self.config.profile` instead of taking individual kwargs
- `packages/aegis_mw/src/aegis_mw/tool_middleware.py` — UPDATE — read `self.profile.rules_tool_call` instead of hard-coded rule list
- `packages/aegis_mw/src/aegis_mw/model_middleware.py` — UPDATE — read `self.profile.rules_pre_inference` (story-mw-03's half) and `self.profile.rules_post_inference` (story-mw-04's half) instead of hard-coded lists
- `packages/aegis_mw/src/aegis_mw/subagent_middleware.py` — UPDATE — read profile from resolved `self.profile`; `per_subagent_profile` values now resolve via `resolve_profile`
- `packages/aegis_mw/src/aegis_mw/agent_middleware.py` — UPDATE — bind `aegis.profile = self.profile.name` to structlog and OTel attributes
- `packages/aegis_mw/src/aegis_mw/__init__.py` — UPDATE — export `Profile`, `DEFAULT_PROFILE`, `FINANCIAL_SERVICES_PROFILE`, `HEALTHCARE_PROFILE`, `PUBLIC_SECTOR_PROFILE`, `resolve_profile`
- `packages/aegis_core/src/aegis_core/errors.py` — UPDATE — add `UnknownProfile(AegisError)` taking the offending name
- `packages/aegis_mw/examples/support_agent.py` — NEW — **the 30-line demo agent** referenced by `docs/PRD.md` "Demo moment" and the README; uses splunklib.ai 3.0.0 with all four Aegis middleware applied via `profile="financial_services"`; ≤ 30 lines excluding imports + blank lines; runnable end-to-end against a Splunk instance (env-gated via `AEGIS_SPLUNK_HOST` etc.)
- `packages/aegis_mw/examples/README.md` — NEW — short doc on how to run `support_agent.py` against Splunk Cloud Explorer Edition; includes the verbatim 3-line integration snippet
- `packages/aegis_mw/tests/test_profiles.py` — NEW — ≥ 16 behavioral tests: all 4 profiles construct (frozen, immutable, hash-stable); FSI profile has "PCI" in `rules_post_inference` AND in `rules_tool_call`; HEALTHCARE profile has "PHI" prominently weighted; PUBSEC profile includes "Code Detection" + "Sensitive Data"; `resolve_profile("financial_services")` returns `FINANCIAL_SERVICES_PROFILE`; `resolve_profile("nonsense")` raises `UnknownProfile`; `resolve_profile(FINANCIAL_SERVICES_PROFILE)` is the identity (passthrough); the same profile passed to all 4 middleware classes results in 4 identical `aegis.profile` OTel attributes (assert via in-memory exporter); `support_agent.py` is ≤ 30 lines via `awk` count
- `packages/aegis_mw/tests/test_support_agent_demo.py` — NEW — ≥ 3 smoke tests that import `examples/support_agent.py` as a module (via importlib), assert it constructs the Agent with all 4 middleware kwargs populated, and that the profile string `"financial_services"` flows through to all 4 middleware instances

The coding agent must NOT modify files outside this map without re-checking `CLAUDE.md`.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given the four canonical profiles are defined
When  `uv run python -c "from aegis_mw import DEFAULT_PROFILE, FINANCIAL_SERVICES_PROFILE, HEALTHCARE_PROFILE, PUBLIC_SECTOR_PROFILE; print(sorted(p.name for p in [DEFAULT_PROFILE, FINANCIAL_SERVICES_PROFILE, HEALTHCARE_PROFILE, PUBLIC_SECTOR_PROFILE]))"` runs
Then  the output is exactly: ['default', 'financial_services', 'healthcare', 'public_sector']

Given resolve_profile is called with each canonical name
When  `uv run python -c "from aegis_mw import resolve_profile; print(all(resolve_profile(n).name == n for n in ['default','financial_services','healthcare','public_sector']))"` runs
Then  the output is "True"

Given resolve_profile is called with an unknown name
When  `uv run python -c "from aegis_mw import resolve_profile; from aegis_core.errors import UnknownProfile; \ntry: resolve_profile('nonsense')\nexcept UnknownProfile: print('ok')"` runs
Then  the output is "ok"

Given FINANCIAL_SERVICES_PROFILE
When  the rule subsets are inspected
Then  "PCI" appears in rules_post_inference AND in rules_tool_call

Given HEALTHCARE_PROFILE
When  the rule subsets are inspected
Then  "PHI" appears in rules_post_inference AND in rules_tool_call

Given PUBLIC_SECTOR_PROFILE
When  the rule subsets are inspected
Then  "Code Detection" appears in rules_post_inference

Given examples/support_agent.py is loaded and executes its construction path
When  `uv run pytest packages/aegis_mw/tests/test_support_agent_demo.py -v` runs
Then  ≥ 3 tests pass; the constructed Agent has all 4 middleware kwargs populated; every middleware instance reports profile.name == "financial_services"

Given examples/support_agent.py exists
When  `grep -v -E '^\s*(#|$|from |import )' packages/aegis_mw/examples/support_agent.py | wc -l` runs
Then  the output is ≤ 30 (the demo body excluding imports / blanks / comments)

Given the test suite is run
When  `uv run pytest packages/aegis_mw/tests/test_profiles.py packages/aegis_mw/tests/test_support_agent_demo.py -v` runs
Then  ≥ 19 tests pass and 0 fail

Given each source file in packages/aegis_mw/src/aegis_mw/
When  `find packages/aegis_mw/src/aegis_mw -name '*.py' -exec wc -l {} +` runs
Then  every file reports ≤ 400 lines

Given the §14 grep is run on changed source (excluding test files and examples/)
When  `grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/profiles.py packages/aegis_mw/src/aegis_mw/config.py` runs
Then  the output is empty
```

---

## Shell verification

The coding agent runs this to confirm the story is done before opening a PR:

```bash
# All 4 profiles resolve and are immutable
uv run python <<'PY'
from aegis_mw import (
    Profile, resolve_profile,
    DEFAULT_PROFILE, FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE, PUBLIC_SECTOR_PROFILE,
)
from aegis_core.errors import UnknownProfile

# Names
names = sorted(p.name for p in [
    DEFAULT_PROFILE, FINANCIAL_SERVICES_PROFILE,
    HEALTHCARE_PROFILE, PUBLIC_SECTOR_PROFILE,
])
assert names == ['default', 'financial_services', 'healthcare', 'public_sector'], names

# resolve_profile by string
for n in names:
    assert resolve_profile(n).name == n

# resolve_profile is identity on Profile instances
assert resolve_profile(FINANCIAL_SERVICES_PROFILE) is FINANCIAL_SERVICES_PROFILE

# Unknown name raises
try:
    resolve_profile('nonsense')
    raise AssertionError('expected UnknownProfile')
except UnknownProfile:
    pass

# FSI emphasizes PCI
assert 'PCI' in FINANCIAL_SERVICES_PROFILE.rules_post_inference
assert 'PCI' in FINANCIAL_SERVICES_PROFILE.rules_tool_call

# HIPAA emphasizes PHI
assert 'PHI' in HEALTHCARE_PROFILE.rules_post_inference
assert 'PHI' in HEALTHCARE_PROFILE.rules_tool_call

# PubSec includes Code Detection
assert 'Code Detection' in PUBLIC_SECTOR_PROFILE.rules_post_inference

# Frozen / hashable
hash(FINANCIAL_SERVICES_PROFILE)
print('OK')
PY
# Must print 'OK'

# Demo agent body ≤ 30 LOC (excludes imports / comments / blank lines)
LINES=$(grep -v -E '^\s*(#|$|from |import )' packages/aegis_mw/examples/support_agent.py | wc -l | tr -d ' ')
echo "support_agent.py body: ${LINES} lines"
[ "${LINES}" -le 30 ]
# Must exit 0

# Tests pass
uv run pytest packages/aegis_mw/tests/test_profiles.py packages/aegis_mw/tests/test_support_agent_demo.py -v 2>&1 | grep -cE "PASSED"
# Must output >= 19

# 400-LOC cap across the package
find packages/aegis_mw/src/aegis_mw -name '*.py' -exec wc -l {} + | awk '$1 > 400 && $2 != "total" { print; exit 1 }'
# Must exit 0

# §14 clean (production code only — examples/ tolerates demo-data labels)
grep -rE "(mock|fake|dummy|hardcoded|simulated)" packages/aegis_mw/src/aegis_mw/profiles.py packages/aegis_mw/src/aegis_mw/config.py
# Must output nothing

# Lint + typecheck
uv run ruff check packages/aegis_mw/
uv run mypy packages/aegis_mw/src/aegis_mw/profiles.py packages/aegis_mw/src/aegis_mw/config.py
# Both must exit 0
```

---

## Notes for coding agent

- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, the public splunklib.ai 3.0.0 API has 4 middleware kwargs: `tool_middleware`, `subagent_middleware`, `model_middleware`, `agent_middleware`.** The `support_agent.py` demo uses ALL FOUR populated with profile-driven Aegis middleware — that is the headline pitch of the README's 3-line integration moment.
- **Per `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7, the 11 canonical AI Defense rule names are verbatim: Code Detection, Harassment, Hate Speech, PCI, PHI, PII, Profanity, Prompt Injection, Sexual Content & Exploitation, Social Division & Polarization, Violence & Public Safety Threats.** Profiles use these exact strings. Include ampersands and spacing exactly.
- **Per `../../../context/sources/code-snippets/splunklib-ai-security-top60.py`, splunklib.ai's cheap-first-pass `detect_injection()` runs the 9 verbatim regex patterns at `splunklib/ai/security.py:24-40`.** All 4 profiles set `escalate_on_first_pass_hit=True` by default — the cheap path catches the obvious 90%, AI Defense handles the borderline 10%.
- **Profile rule subsets — the wedge.** Each profile picks a subset of the 11 AI Defense rules for each middleware layer:
  - `DEFAULT_PROFILE`: `rules_pre_inference=("Prompt Injection",)`, `rules_post_inference=("PII","PHI","PCI","Code Detection")`, `rules_tool_call=("Prompt Injection","Code Detection")`, `foundation_sec_enabled=True`, `escalate_on_first_pass_hit=True`
  - `FINANCIAL_SERVICES_PROFILE`: `rules_post_inference=("PCI","PII","Code Detection","Sensitive Data")`, `rules_tool_call=("Prompt Injection","PCI","Code Detection")`, otherwise like default — PCI emphasis is the differentiator
  - `HEALTHCARE_PROFILE`: `rules_post_inference=("PHI","PII","Code Detection")`, `rules_tool_call=("Prompt Injection","PHI")`, otherwise like default — PHI emphasis
  - `PUBLIC_SECTOR_PROFILE`: `rules_post_inference=("PII","Code Detection","Violence & Public Safety Threats","Social Division & Polarization")`, `rules_tool_call=("Prompt Injection","Code Detection")`, otherwise like default — compliance + content emphasis
- **The 30-line `examples/support_agent.py` is the demo moment** referenced in `docs/PRD.md` and the README. Keep the body to ≤ 30 non-blank non-comment non-import lines. Skeleton:
  ```python
  import asyncio, os
  from splunklib.ai import Agent, OpenAIModel
  from splunklib.client import connect
  from aegis_mw import (
      SafetyToolMiddleware, SafetyModelMiddleware,
      SafetySubagentMiddleware, SafetyAgentMiddleware,
  )

  async def main() -> None:
      service = connect(host=os.environ["AEGIS_SPLUNK_HOST"], ...)
      model = OpenAIModel(model="gpt-4o", api_key=os.environ["OPENAI_API_KEY"], base_url="...")
      profile = "financial_services"
      agent = Agent(
          model=model,
          system_prompt="You are a Splunk support agent.",
          service=service,
          tool_middleware=[SafetyToolMiddleware(profile=profile)],
          model_middleware=[SafetyModelMiddleware(profile=profile)],
          subagent_middleware=[SafetySubagentMiddleware(profile=profile)],
          agent_middleware=[SafetyAgentMiddleware(profile=profile)],
      )
      async with agent:
          response = await agent.invoke_with_data(
              "Summarize this customer record.",
              {"name": "Jane Doe", "card_last4": "1234"},
          )
      print(response)

  if __name__ == "__main__":
      asyncio.run(main())
  ```
  The body (after imports, after blanks/comments) must be ≤ 30 lines. The test counts lines via `grep -v -E '^\s*(#|$|from |import )'`.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, `Agent` is an `AsyncContextManager` and MUST be used with `async with` — the demo does this.** The `invoke_with_data(instructions, data)` form (`agent.py:296-311`) wraps with `create_structured_prompt` automatically — perfect for the demo's "untrusted customer data" framing.
- **Per `../../../context/02-agent-frameworks/06-splunklib-ai-deep-read.md`, splunklib.ai 3.0.0 hard-requires Python 3.13.** The example will not run on older interpreters; the `examples/README.md` must say so.
- **Per `../../../context/HALLUCINATION-AUDIT.md`, `AgentLimits` has the typo `max_structured_output_retires` (sic — defaults: token=200_000, steps=100, timeout=600s, structured-output-retries=3).** This story does not need to touch `AgentLimits`; if you reference it in the demo to override a default, preserve the typo. Otherwise leave it at the splunklib.ai default.
- The "Sensitive Data" rule name used in FSI/PubSec profiles is NOT in the public-docs 11-rule list — it appears in DefenseClaw's extra rule set (per the `../../../context/07-cisco-stack/01-ai-defense-deep.md` §7 contradiction note, DefenseClaw adds Jailbreak, Sensitive Data, Data Leakage). Document this in the profile docstring: "Sensitive Data is supplied by the DefenseClaw rule pack and is a no-op at the AI Defense Inspection API layer." The `aegis_judges.ai_defense.inspect()` client should silently drop unknown rule names sent to AI Defense (or warn-log them) — that contract was set in EPIC-04.

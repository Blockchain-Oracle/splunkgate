# Story — Template-based verdict explainer (v1 of EPIC-05)

**ID:** story-explainer-01-template-based-verdict-explainer
**Epic:** EPIC-05 — Verdict explainer (template v1, Foundation-Sec future)
**Depends on:** story-core-01-verdict-pydantic-types
**Estimate:** ~1h (~30 LOC src + ~60 LOC tests)
**Status:** PENDING
**Added:** 2026-06-05 (per ADR-013 — replaces deferred Foundation-Sec stories foundsec-02 + foundsec-03)

---

## Why this story exists (read ADR-013 first)

ADR-013 deferred the Foundation-Sec invocation stories because Splunk Hosted Models access is undocumented for Trial-tier Cloud tenants (confirmed via live Playwright probe + AITK 5.7.4 official docs + Splunk Feb 18 2026 launch blog). The Verdict shape (`packages/splunkgate_core/src/splunkgate_core/verdict.py`) has an `explanation: str | None` field that the dashboards, regulator-evidence-pack PDF, and demo video all surface. Something has to populate it.

This story ships a **deterministic, template-based explainer** that:
- Takes a `Verdict` plus an optional `VerdictContext`. The Verdict supplies `verdict`, `severity`, `rules`, and `modifications` (which carries `redacted_text` when MODIFY). The VerdictContext is agent-side state (model name, system prompt summary, recent messages, surface) that a smarter future explainer will reference when composing prompts — the v1 template doesn't need it but accepts it for forward compatibility.
- Returns a human-readable explanation string built from `verdict.verdict`, `verdict.severity`, `verdict.rules` (rule names + sources), and `verdict.modifications.get("redacted_text")` when present
- Has **zero external dependencies** (no model inference, no HTTP, no SPL)
- Preserves the ADR-003 invariant (explainer-only, never classifier)
- Is structurally swappable for the future Foundation-Sec implementation: same function signature, same output type

When Splunk Slack confirms the Hosted Models access path, replacing this with a real Foundation-Sec call is a one-file swap inside `splunkgate_judges/explainer.py`. The Foundation-Sec implementation will use both inputs (Verdict + VerdictContext) to compose a richer `| ai` prompt; the v1 template ignores the optional context.

---

## File modification map

- `packages/splunkgate_judges/src/splunkgate_judges/explainer.py` — NEW — ~30 LOC. Single module containing `explain_verdict(ctx: VerdictContext) -> str`. No I/O, no async, no external deps. Pure function over `splunkgate_core` types.
- `packages/splunkgate_judges/src/splunkgate_judges/__init__.py` — UPDATE — export `explain_verdict` so `from splunkgate_judges import explain_verdict` works.
- `packages/splunkgate_judges/tests/test_explainer.py` — NEW — ~60 LOC. Behavioral tests for every branch.

---

## Function shape

```python
from splunkgate_core import Verdict, VerdictContext

def explain_verdict(verdict: Verdict, ctx: VerdictContext | None = None) -> str:
    """Return a human-readable explanation string for a Verdict.

    Deterministic and dependency-free. Replaceable with a Foundation-Sec
    call when Splunk Hosted Models access is unblocked (see ADR-013).

    Invariant: this function NEVER returns a verdict label or severity —
    only a free-text WHY-string for human consumption. Per ADR-003,
    Foundation-Sec (and any successor explainer) is explainer-only.

    The optional `ctx` is unused by the v1 template implementation; the
    parameter exists so the signature is forward-compatible with the
    future Foundation-Sec implementation, which will reference agent
    state to compose richer prompts.
    """
```

The implementation composes a short paragraph from `verdict.verdict` (the label), `verdict.severity`, `verdict.rules` (rule names + sources), and `verdict.modifications.get("redacted_text")` when MODIFY. No more than ~280 characters per typical input.

---

## Acceptance criteria (BDD — machine-verifiable)

```
Given a Verdict with verdict=BLOCK, severity=HIGH, rules=[RuleHit(rule="Prompt Injection", confidence=1.0, source="ai_defense")]
When  explain_verdict(verdict) is called (no ctx)
Then  the returned string contains "Prompt Injection" AND "BLOCK" AND "HIGH"
And   the string does NOT contain literal None or null

Given a Verdict with verdict=ALLOW, severity=NONE_SEVERITY, rules=[]
When  explain_verdict(verdict) is called
Then  the returned string is non-empty
And   contains the word "ALLOW" or "no rules" or "safe"

Given a Verdict with multiple rules from different sources
When  explain_verdict(verdict) is called
Then  every rule name appears in the output exactly once
And   the source for each rule is preserved (e.g., "ai_defense" or "splunklib_security")

Given two distinct Verdict instances with identical field values
When  explain_verdict is called on both
Then  the two output strings are byte-equal (determinism — no random / timestamp / process-state input)

Given a Verdict with verdict=MODIFY and modifications={"redacted_text": "[REDACTED PII]"}
When  explain_verdict(verdict) is called
Then  the output references the redaction but does NOT inline raw PII patterns

Given a Verdict and a VerdictContext that both populated
When  explain_verdict(verdict, ctx) is called
Then  the result is byte-equal to explain_verdict(verdict, None)
And   the v1 template implementation has not used ctx (forward-compat parameter only)

Given the test file
When  `uv run pytest packages/splunkgate_judges/tests/test_explainer.py -v` runs
Then  ≥ 5 tests pass and 0 fail

Given the src file
When  `uv run mypy --strict packages/splunkgate_judges/src/splunkgate_judges/explainer.py` runs
Then  exit code is 0

Given the src file
When  `wc -l packages/splunkgate_judges/src/splunkgate_judges/explainer.py` runs
Then  the line count is ≤ 60 (well under the 400 cap)
```

---

## Shell verification

```bash
cd packages/splunkgate_judges
uv run pytest tests/test_explainer.py -v 2>&1 | grep -cE "PASSED" # must output >= 5
uv run mypy --strict -p splunkgate_judges                                # must exit 0
test "$(wc -l < src/splunkgate_judges/explainer.py)" -le 60 || exit 1
echo OK
```

---

## Notes for coding agent

- **No HTTP, no async, no model inference.** This is a pure, side-effect-free function. Tests do not need `respx` or `pytest-asyncio`.
- The explainer **does not classify**. It composes a string from already-decided verdict fields. The classification (BLOCK / ALLOW / MODIFY) comes from `pre_inference_scan` in `splunkgate_mw/model_middleware.py` and the Cisco AI Defense client; this story only renders the result.
- Per ADR-003, `RuleHit.source` is `Literal["ai_defense", "defenseclaw_regex", "splunklib_security"]`. The explainer must surface the source verbatim in the output string so the reader knows which evaluator fired.
- **The `ctx: VerdictContext | None` parameter is forward-compat only in v1.** The template body does not read from `ctx`. Tests should explicitly assert that passing the same `Verdict` with or without `ctx` produces byte-equal output (so we have a regression guard the day someone is tempted to add `ctx`-dependent behavior without thinking it through).
- **Future swap point:** when Splunk Slack confirms Hosted Models access, replace the body of `explain_verdict` with a `| ai prompt=... provider=splunk_hosted` SPL call. The function signature stays. The Foundation-Sec implementation will use `ctx` to compose a richer prompt; downstream callers (S1 middleware, S4 dashboards, eval harness) do not change.
- The redacted text lives at `verdict.modifications.get("redacted_text")` — `Verdict.modifications` is typed as `dict[str, object] | None` per `packages/splunkgate_core/src/splunkgate_core/verdict.py`. Defensive-read for None.
- Keep the explanation under ~280 characters typical — it lands in a Splunk dashboard cell and a PDF regulator-evidence-pack table cell, both of which truncate longer strings.
- Cite ADR-013 in the module docstring header so future readers understand why this isn't an `| ai` call.

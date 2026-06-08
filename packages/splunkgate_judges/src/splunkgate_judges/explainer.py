"""Template-based verdict explainer — v1 of EPIC-05 per ADR-013.

Returns a deterministic, dependency-free human-readable WHY-string for a
`Verdict`. Replaceable with a Foundation-Sec `| ai` SPL call when Splunk
Slack confirms Trial-tier Hosted Models access (see ADR-013 in
docs/architecture.md). Per ADR-003, this function is explainer-only; it
never returns a verdict label or classification.

The optional `ctx: VerdictContext` parameter is forward-compatibility
only — v1 ignores it. The future Foundation-Sec implementation will use
ctx (agent_id, model_name, system_prompt_summary, recent_messages) to
compose richer prompts.
"""

from splunkgate_core import Verdict, VerdictContext, VerdictLabel

__all__ = ["explain_verdict"]


def explain_verdict(verdict: Verdict, ctx: VerdictContext | None = None) -> str:
    """Compose a one-paragraph explanation of a verdict for human consumption.

    Output is ≤ 280 characters typical so it fits Splunk dashboard cells and
    PDF regulator-evidence-pack rows without truncation. The string surfaces
    every rule name + source from `verdict.rules` (one-shot, no dedup needed
    because RuleHit equality is value-based and the caller controls input).
    """
    _ = ctx  # forward-compat; intentionally unused in v1
    label = verdict.verdict.value
    severity = verdict.severity.value
    if not verdict.rules:
        return f"{label} (severity {severity}): no rules fired; input deemed safe."
    rule_phrases = [f"{r.rule} [{r.source}]" for r in verdict.rules]
    body = ", ".join(rule_phrases)
    mods = verdict.modifications or {}
    redacted = mods.get("redacted_text")
    if verdict.verdict is VerdictLabel.MODIFY and redacted is not None:
        return f"{label} (severity {severity}): {body}; content was redacted."
    return f"{label} (severity {severity}): {body}."

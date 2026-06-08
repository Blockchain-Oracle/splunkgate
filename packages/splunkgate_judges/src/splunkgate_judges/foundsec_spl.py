"""Foundation-Sec invocation via Splunk's `| ai` SPL command.

Implements the inline-SPL pattern surfaced by SebAustin/aria
(another Splunk Agentic Ops 2026 entry, MIT) — the only public repo
that actually wires the canonical Hosted Models call shape:

    | makeresults
    | eval prompt="..."
    | ai prompt=prompt provider=Splunk model=foundation-sec-1.1-8b-instruct

This module is **mock-by-default** (env `SPLUNKGATE_USE_MOCK=true`).
Reason: per ADR-013, Trial-tier Splunk Cloud tenants have an
unverified Hosted Models entitlement path. Aria handles the same gap
with `ARIA_USE_MOCK=true`; we mirror the pattern so judges running the
demo without entitlement see deterministic explanations (the existing
story-explainer-01 template) rather than empty / errored output.

Operators with confirmed Hosted Models access flip
`SPLUNKGATE_USE_MOCK=false` and the live `| ai` SPL runs against their
search head. The same `Verdict` shape flows through both paths.

Per ADR-003: Foundation-Sec is EXPLAINER-only, never classifier. The
verdict label + severity + rules come from the AI Defense binary
classifier upstream; this module only generates the WHY-string.

The build_ai_spl() function is pure — no I/O, no env reads, no
splunklib dependency. The explain_via_ai_spl() wrapper does the env
read + service call + template fallback chain.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog

from splunkgate_judges.explainer import explain_verdict

if TYPE_CHECKING:
    from splunkgate_core import Verdict, VerdictContext
    from splunklib.client import Service

_logger = structlog.get_logger(__name__)

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "MOCK_ENV_VAR",
    "build_ai_spl",
    "explain_via_ai_spl",
]

# Canonical Splunk Hosted Models triple. Pinned here so a future model
# bump is a one-line change in this file. Foundation-Sec model name verbatim
# per Splunk Hosted Models docs (GA Feb 18 2026).
DEFAULT_PROVIDER = "Splunk"
DEFAULT_MODEL = "foundation-sec-1.1-8b-instruct"

# Cap the prompt so we stay well inside Foundation-Sec's context window and
# never blow the SPL command-line limit. The ceiling is conservative —
# tightening to 280 chars matches the template explainer's output budget.
_PROMPT_CHAR_CAP = 1200

# Env-var sentinel for the mock-default toggle. Truthy values
# ("1", "true", "yes" — case-insensitive) keep the live SPL call OFF.
MOCK_ENV_VAR = "SPLUNKGATE_USE_MOCK"
_TRUTHY = {"1", "true", "yes", "y", "on"}


def _is_mock_mode() -> bool:
    """Return True iff `SPLUNKGATE_USE_MOCK` is unset OR truthy.

    Default-on: absence of the env var means mock. Operators must
    explicitly opt in to live calls by setting it to a falsey value.
    """
    raw = os.environ.get(MOCK_ENV_VAR, "true")
    return raw.strip().lower() in _TRUTHY


def _escape_for_spl(value: str) -> str:
    """Escape backslash + double-quote for inclusion in an SPL `eval` literal.

    Newlines collapse to spaces — `| ai prompt=...` expects a single-line
    string. Truncated to `_PROMPT_CHAR_CAP` chars; tail is replaced with
    an ellipsis sentinel so the prompt remains valid UTF-8.
    """
    flat = " ".join(value.split())
    escaped = flat.replace("\\", "\\\\").replace('"', '\\"')
    if len(escaped) > _PROMPT_CHAR_CAP:
        return escaped[: _PROMPT_CHAR_CAP - 3] + "..."
    return escaped


def _build_prompt(verdict: Verdict, ctx: VerdictContext | None) -> str:
    """Compose the natural-language prompt fed to Foundation-Sec.

    Surfaces: verdict label, severity, every rule + its source, and
    (when ctx is provided) agent_id + model_name so the explainer can
    name the affected actor in the WHY-string.
    """
    label = verdict.verdict.value
    severity = verdict.severity.value
    rule_phrases = [f"{r.rule} (source={r.source})" for r in verdict.rules]
    rules = ", ".join(rule_phrases) if rule_phrases else "no rules"
    head = (
        "You are Foundation-Sec, a security copilot. Explain this AI safety "
        f"verdict in one sentence (<=280 chars). Verdict={label}, severity="
        f"{severity}, rules={rules}."
    )
    if ctx is not None:
        head += f" Agent={ctx.agent_id}, model={ctx.model_name}, surface={ctx.surface}."
    return head


def build_ai_spl(verdict: Verdict, ctx: VerdictContext | None = None) -> str:
    """Build the literal SPL command to send to a Splunk search head.

    Pure function — no I/O, no env reads. Composable with any executor
    (splunklib oneshot, MCP `splunk_run_query`, raw REST `/services/search/jobs`).

    Pattern attribution: SebAustin/aria, splunk-agentic-ops-hackathon 2026.
    """
    prompt = _escape_for_spl(_build_prompt(verdict, ctx))
    return (
        f'| makeresults | eval prompt="{prompt}" '
        f"| ai prompt=prompt provider={DEFAULT_PROVIDER} model={DEFAULT_MODEL} "
        "| fields explanation"
    )


def explain_via_ai_spl(
    verdict: Verdict,
    ctx: VerdictContext | None = None,
    *,
    service: Service | None = None,
) -> str:
    """Return a Foundation-Sec-authored explanation OR the template fallback.

    Chain: (1) if mock mode is on, short-circuit to the template explainer;
    (2) otherwise execute the SPL via `service.jobs.oneshot()` and read the
    first row's `explanation` field; (3) on any exception, fall back to the
    template explainer so the caller always gets a non-empty string.

    The `service` argument is the splunklib.client.Service the caller
    already authenticated. We deliberately do not construct one here —
    auth + endpoint discovery belong to the integration layer.
    """
    in_mock = _is_mock_mode()
    if in_mock:
        # Operator wired up a service but mock mode silently ignored it —
        # almost always a config mistake. Log loud so they notice.
        if service is not None:
            _logger.warning(
                "splunkgate.explainer.service_ignored_in_mock_mode",
                trace_id=str(verdict.trace_id),
            )
        else:
            _logger.info(
                "splunkgate.explainer.mode",
                mode="mock",
                reason="env_default",
                trace_id=str(verdict.trace_id),
            )
        return explain_verdict(verdict, ctx)
    if service is None:
        # Live mode requested but no service to run the SPL — same string
        # output as mock, but the operator should know live was unreachable.
        _logger.warning(
            "splunkgate.explainer.live_no_service",
            trace_id=str(verdict.trace_id),
        )
        return explain_verdict(verdict, ctx)

    _logger.info("splunkgate.explainer.mode", mode="live", trace_id=str(verdict.trace_id))
    try:
        spl = build_ai_spl(verdict, ctx)
        # splunklib oneshot returns a ResultsReader; first dict's
        # `explanation` field is what `| ai` writes by convention.
        # Deferred import keeps splunklib optional for mock-mode users.
        from splunklib.results import JSONResultsReader  # noqa: PLC0415

        stream = service.jobs.oneshot(spl, output_mode="json")
        first_row_keys: list[str] = []
        for row in JSONResultsReader(stream):
            if isinstance(row, dict):
                if not first_row_keys:
                    first_row_keys = list(row.keys())
                explanation = row.get("explanation")
                if isinstance(explanation, str) and explanation.strip():
                    return explanation.strip()
        # Empty / malformed response — log row keys so operators can debug
        # field-name drift (`| ai` may emit a different column name on a
        # future Splunk release) before falling through to template.
        _logger.warning(
            "splunkgate.explainer.no_explanation_in_response",
            row_keys=first_row_keys,
            trace_id=str(verdict.trace_id),
        )
        return explain_verdict(verdict, ctx)
    except Exception as exc:  # noqa: BLE001 — template fallback is the contract
        # Auth, DNS, splunklib import, `| ai` command missing on the search
        # head — all surface here. Fallback string preserves the chain but
        # the exception class + message MUST be visible so live-call
        # regressions don't look like a clean mock run.
        _logger.warning(
            "splunkgate.explainer.live_call_failed",
            exc_class=type(exc).__name__,
            exc_msg=str(exc),
            trace_id=str(verdict.trace_id),
        )
        return explain_verdict(verdict, ctx)

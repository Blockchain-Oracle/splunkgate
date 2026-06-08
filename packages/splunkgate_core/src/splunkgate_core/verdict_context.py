"""VerdictContext — the agent-side context passed to the explainer.

Per ADR-003, the explainer is EXPLAINER-only (not classifier); it never
populates RuleHit.source. It receives VerdictContext alongside the live
Verdict so it can compose a human-readable WHY-string referencing agent state.

Per ADR-013 (2026-06-05), the v1 explainer is `splunkgate_judges.explainer.explain_verdict`
(template-based, deterministic). The future Foundation-Sec implementation is
the swap target once Splunk Hosted Models access is unblocked; the same
VerdictContext shape is the input to both.

Used by:
- splunkgate_judges.explainer (v1)
- splunkgate_mw post-tool / post-inference hooks
- splunkgate_mcp tool handlers
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VerdictContext(BaseModel):
    """Snapshot of agent state carried alongside a Verdict for the explainer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: UUID
    agent_id: str
    model_name: str
    system_prompt_summary: str
    recent_messages: list[str]
    surface: Literal[
        "mw_model",
        "mw_tool",
        "mw_subagent",
        "mcp_score",
        "mcp_judge_tool",
        "mcp_check_output",
        "mcp_audit",
        "defenseclaw",
    ]

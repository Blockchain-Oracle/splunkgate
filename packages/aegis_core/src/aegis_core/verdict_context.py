"""VerdictContext — the agent-side context passed to Foundation-Sec for explanations.

Per ADR-003, Foundation-Sec is positioned as an EXPLAINER (not classifier);
it never populates RuleHit.source. It receives VerdictContext alongside the
live Verdict so it can compose an SPL `| ai` prompt referencing agent state.

Used by:
- story-foundsec-02 (build_explanation_spl signature)
- aegis_mw post-tool / post-inference hooks
- aegis_mcp tool handlers
- aegis_judges DefenseClaw shim
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

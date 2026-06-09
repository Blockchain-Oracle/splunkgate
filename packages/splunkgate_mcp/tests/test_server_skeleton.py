"""Behavioral tests for story-mcp-01: SplunkGate MCP server skeleton."""

from __future__ import annotations

import splunkgate_mcp
from splunkgate_core.verdict import Verdict
from splunkgate_mcp.schemas import VERDICT_OUTPUT_SCHEMA


def test_version_is_0_1_0() -> None:
    """Package version bumped from 0.0.1 stub to 0.1.0 first-real-skeleton."""
    assert splunkgate_mcp.__version__ == "0.1.0"


def test_verdict_output_schema_matches_pydantic() -> None:
    """schemas.VERDICT_OUTPUT_SCHEMA must equal Verdict.model_json_schema()."""
    assert Verdict.model_json_schema() == VERDICT_OUTPUT_SCHEMA

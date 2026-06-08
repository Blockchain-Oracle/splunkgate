"""Behavioral tests for VerdictContext."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from splunkgate_core.verdict_context import VerdictContext


def _ctx(**overrides: object) -> VerdictContext:
    base: dict[str, object] = {
        "trace_id": uuid4(),
        "agent_id": "agent-1",
        "model_name": "gpt-4o-mini",
        "system_prompt_summary": "you are helpful",
        "recent_messages": ["user: hi", "assistant: hi"],
        "surface": "mw_model",
    }
    base.update(overrides)
    return VerdictContext(**base)  # type: ignore[arg-type]


def test_verdict_context_constructs_with_required_fields() -> None:
    ctx = _ctx()
    assert ctx.surface == "mw_model"
    assert ctx.recent_messages == ["user: hi", "assistant: hi"]


def test_verdict_context_rejects_unknown_surface() -> None:
    with pytest.raises(ValidationError):
        _ctx(surface="nonsense_surface")


def test_verdict_context_round_trips_through_json() -> None:
    ctx = _ctx()
    raw = ctx.model_dump_json()
    restored = VerdictContext.model_validate_json(raw)
    assert restored == ctx


def test_verdict_context_rejects_non_uuid_trace_id() -> None:
    with pytest.raises(ValidationError):
        _ctx(trace_id="not-a-uuid")


def test_verdict_context_accepts_empty_recent_messages() -> None:
    ctx = _ctx(recent_messages=[])
    assert ctx.recent_messages == []


def test_verdict_context_extra_forbid_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        _ctx(unexpected_field="value")


def test_verdict_context_json_schema_has_all_six_properties() -> None:
    schema = VerdictContext.model_json_schema()
    expected = {
        "trace_id",
        "agent_id",
        "model_name",
        "system_prompt_summary",
        "recent_messages",
        "surface",
    }
    assert expected <= set(schema["properties"].keys())

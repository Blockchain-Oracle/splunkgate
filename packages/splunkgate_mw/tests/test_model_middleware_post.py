"""Behavioral tests for SafetyModelMiddleware post-inference scan (story-mw-04)."""

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from splunkgate_core.errors import ModelOutputBlockedBySplunkGate
from splunkgate_core.verdict import (
    Severity,
    VerdictLabel,
)
from splunkgate_judges.ai_defense_mock import MockAIDefenseClient
from splunkgate_judges.ai_defense_types import (
    AIDefenseRule,
    Classification,
    InspectRequest,
    InspectResponse,
)
from splunkgate_judges.ai_defense_types import (
    RuleHit as InspectRuleHit,
)
from splunkgate_mw import _post_inference
from splunkgate_mw._post_inference import post_inference_scan
from splunkgate_mw.config import Config
from splunkgate_mw.model_middleware import SafetyModelMiddleware
from splunkgate_mw.profiles import Profile
from splunklib.ai.messages import AIMessage, HumanMessage
from splunklib.ai.middleware import AgentState, ModelRequest, ModelResponse


class _MediumSeverityClient:
    """Minimal AIDefenseLike that returns MEDIUM severity + a PII rule hit.

    Used to exercise the MODIFY → [REDACTED] branch of post_inference_scan
    deterministically. The substring-mode MockAIDefenseClient picks the
    highest-severity fixture for any matched phrase which would force BLOCK;
    this stub is the cleanest way to exercise MODIFY without depending on
    fixture-matrix behavior.
    """

    async def inspect_chat(
        self,
        request: InspectRequest,
        *,
        trace_id: str | None = None,
    ) -> InspectResponse:
        _ = request, trace_id
        return InspectResponse(
            is_safe=False,
            severity=Severity.MEDIUM,
            rules=[
                InspectRuleHit(
                    rule_name=AIDefenseRule.PII,
                    classification=Classification.PRIVACY_VIOLATION,
                )
            ],
        )


# The fixture triggers carry a "[tier:*]" suffix. The MockAIDefenseClient also
# substring-matches the phrase part (after the substring-match fix in PR #84).
# We use the bare phrase to keep tests readable.
_PII_PHRASE = "my ssn is 123-45-6789"
_PCI_PHRASE = "my card is 4242 4242 4242 4242"
_BENIGN = "the weather looks nice today"


def _request(content: str = "hello") -> ModelRequest:
    state = AgentState(
        messages=cast("Sequence[object]", [HumanMessage(content=content)]),
        thread_id="test-thread",
    )
    return ModelRequest(system_message="be helpful", state=state)


def _response(text: str) -> ModelResponse:
    return ModelResponse(message=AIMessage(content=text, calls=[]))


_Handler = Callable[[ModelRequest], Awaitable[ModelResponse]]


def _handler_returning(text: str) -> _Handler:
    async def handler(_req: ModelRequest) -> ModelResponse:
        return _response(text)

    return handler


# ─── post_inference_scan: pure-function tests ────────────────────────────────


@pytest.mark.asyncio
async def test_post_scan_allows_benign_output() -> None:
    verdict = await post_inference_scan(
        _response(_BENIGN),
        Profile(name="default", description=""),
        Config(),
        ai_defense=MockAIDefenseClient(),
    )
    assert verdict.verdict is VerdictLabel.ALLOW
    assert verdict.severity is Severity.NONE_SEVERITY
    assert verdict.rules == []
    assert verdict.surface == "mw_model"


@pytest.mark.asyncio
async def test_post_scan_allows_when_no_client() -> None:
    """No AI Defense client wired → ALLOW (cannot classify without it)."""
    verdict = await post_inference_scan(
        _response(_PII_PHRASE),
        Profile(name="default", description=""),
        Config(),
        ai_defense=None,
    )
    assert verdict.verdict is VerdictLabel.ALLOW


@pytest.mark.asyncio
async def test_post_scan_pii_returns_ai_defense_sourced_rules() -> None:
    """Renamed in PR #92 fix-up for honesty: substring-mode mock returns
    HIGH-severity → BLOCK for the bare PII phrase. This test asserts ONLY
    the rule-shape + source invariant. The BLOCK path is covered by
    test_post_scan_high_severity_blocks; the MODIFY → [REDACTED] path
    is covered by test_post_scan_medium_severity_modifies_with_redacted_text
    and test_middleware_post_modify_returns_redacted_response.
    """
    verdict = await post_inference_scan(
        _response(_PII_PHRASE),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=False),
        ai_defense=MockAIDefenseClient(),
    )
    assert verdict.verdict is not VerdictLabel.ALLOW
    assert any(r.rule == "PII" for r in verdict.rules)
    assert all(r.source == "ai_defense" for r in verdict.rules)


@pytest.mark.asyncio
async def test_post_scan_high_severity_blocks() -> None:
    verdict = await post_inference_scan(
        _response(_PCI_PHRASE),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=False),
        ai_defense=MockAIDefenseClient(),
    )
    assert verdict.verdict is VerdictLabel.BLOCK
    assert verdict.severity is Severity.HIGH
    assert any(r.rule == "PCI" for r in verdict.rules)


@pytest.mark.asyncio
async def test_post_scan_populates_explanation_when_foundation_sec_enabled() -> None:
    """foundation_sec_enabled=True → explain_verdict produces a WHY-string."""
    verdict = await post_inference_scan(
        _response(_PII_PHRASE),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=True),
        ai_defense=MockAIDefenseClient(),
    )
    assert verdict.verdict is not VerdictLabel.ALLOW
    assert verdict.explanation is not None
    assert "PII" in verdict.explanation
    assert "ai_defense" in verdict.explanation


@pytest.mark.asyncio
async def test_post_scan_skips_explanation_when_foundation_sec_disabled() -> None:
    verdict = await post_inference_scan(
        _response(_PII_PHRASE),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=False),
        ai_defense=MockAIDefenseClient(),
    )
    assert verdict.verdict is not VerdictLabel.ALLOW
    assert verdict.explanation is None


@pytest.mark.asyncio
async def test_post_scan_verdict_has_valid_trace_id() -> None:
    verdict = await post_inference_scan(
        _response(_BENIGN),
        Profile(name="default", description=""),
        Config(),
        ai_defense=MockAIDefenseClient(),
    )
    assert isinstance(verdict.trace_id, UUID)


# ─── SafetyModelMiddleware end-to-end: pre + post seam ───────────────────────


@pytest.mark.asyncio
async def test_middleware_allow_passthrough_returns_original_response() -> None:
    mw = SafetyModelMiddleware(ai_defense=MockAIDefenseClient())
    original = _response(_BENIGN)

    async def handler(_req: ModelRequest) -> ModelResponse:
        return original

    result = await mw.model_middleware(_request(), handler)
    assert result is original


@pytest.mark.asyncio
async def test_middleware_post_inference_block_raises_model_output_blocked() -> None:
    mw = SafetyModelMiddleware(ai_defense=MockAIDefenseClient())
    with pytest.raises(ModelOutputBlockedBySplunkGate) as exc_info:
        await mw.model_middleware(_request(), _handler_returning(_PCI_PHRASE))
    assert exc_info.value.verdict.verdict is VerdictLabel.BLOCK
    assert exc_info.value.verdict.severity is Severity.HIGH


@pytest.mark.asyncio
async def test_middleware_post_inference_block_attaches_explanation() -> None:
    mw = SafetyModelMiddleware(
        ai_defense=MockAIDefenseClient(),
        config=Config(foundation_sec_enabled=True),
    )
    with pytest.raises(ModelOutputBlockedBySplunkGate) as exc_info:
        await mw.model_middleware(_request(), _handler_returning(_PCI_PHRASE))
    assert exc_info.value.verdict.explanation is not None
    assert "BLOCK" in exc_info.value.verdict.explanation


@pytest.mark.asyncio
async def test_middleware_allow_passthrough_preserves_structured_output() -> None:
    """Renamed from the prior misleadingly-named structured-output test:
    this verifies that ALLOW passthrough preserves structured_output. The
    actual MODIFY-path coverage is below in
    test_middleware_post_modify_returns_redacted_response.
    """
    sentinel = object()
    resp = ModelResponse(
        message=AIMessage(content=_BENIGN, calls=[]),
        structured_output=sentinel,
    )

    async def handler(_req: ModelRequest) -> ModelResponse:
        return resp

    mw = SafetyModelMiddleware(ai_defense=MockAIDefenseClient())
    result = await mw.model_middleware(_request(), handler)
    assert result.structured_output is sentinel


# ─── MODIFY branch — uses _MediumSeverityClient stub (PR #92 review fix) ─────


@pytest.mark.asyncio
async def test_post_scan_medium_severity_modifies_with_redacted_text() -> None:
    """Unit-level MODIFY assertion on post_inference_scan."""
    verdict = await post_inference_scan(
        _response("anything triggers MEDIUM here"),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=False),
        ai_defense=_MediumSeverityClient(),
    )
    assert verdict.verdict is VerdictLabel.MODIFY
    assert verdict.severity is Severity.MEDIUM
    assert verdict.modifications == {"redacted_text": "[REDACTED]"}
    assert any(r.rule == "PII" for r in verdict.rules)


@pytest.mark.asyncio
async def test_middleware_post_modify_returns_redacted_response() -> None:
    """End-to-end MODIFY path through _apply_post_scan: original model output
    is replaced by a ModelResponse with content="[REDACTED]", and the
    structured_output proxy is preserved unchanged.
    """
    sentinel = object()
    original = ModelResponse(
        message=AIMessage(content="my ssn is somewhere in here", calls=[]),
        structured_output=sentinel,
    )

    async def handler(_req: ModelRequest) -> ModelResponse:
        return original

    mw = SafetyModelMiddleware(ai_defense=_MediumSeverityClient())
    result = await mw.model_middleware(_request(), handler)

    assert result is not original  # new ModelResponse constructed
    assert result.message.content == "[REDACTED]"
    assert result.structured_output is sentinel


@pytest.mark.asyncio
async def test_middleware_post_modify_carries_explanation_when_enabled() -> None:
    """MODIFY path with foundation_sec_enabled=True: the verdict's
    explanation field is populated (and observable via the OTel emitter,
    which is exercised in the pre-tests). We assert via post_inference_scan
    directly to keep the test focused on the explainer wiring.
    """
    verdict = await post_inference_scan(
        _response("model emitted PII"),
        Profile(name="default", description=""),
        Config(foundation_sec_enabled=True),
        ai_defense=_MediumSeverityClient(),
    )
    assert verdict.verdict is VerdictLabel.MODIFY
    assert verdict.explanation is not None
    assert "MODIFY" in verdict.explanation
    assert "PII" in verdict.explanation


# ─── File-level meta tests (story-mw-04 requirements) ────────────────────────


def test_model_middleware_file_under_400_loc() -> None:
    src = Path(__file__).parents[1] / "src" / "splunkgate_mw" / "model_middleware.py"
    line_count = sum(1 for _ in src.read_text(encoding="utf-8").splitlines())
    assert line_count <= 400, f"model_middleware.py is {line_count} LOC (cap 400)"


def test_post_inference_module_exists_and_exports_scan() -> None:
    """The story mandates a _post_inference.py helper module."""
    assert hasattr(_post_inference, "post_inference_scan")


def test_post_inference_anchor_comments_still_present() -> None:
    """Story-mw-04 inserts CODE at the two anchor sites; the anchors stay as
    permanent inline citations so future readers can find the seam history.
    """
    src = (Path(__file__).parents[1] / "src" / "splunkgate_mw" / "model_middleware.py").read_text(
        encoding="utf-8"
    )
    assert src.count("POST-INFERENCE SCAN: see story-mw-04") == 2

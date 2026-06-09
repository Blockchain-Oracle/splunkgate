"""Behavioral tests for the DefenseClaw regex backend (story-judges-06).

Asserts the cheap-first-pass classifier from `defenseclaw_backend.py`
detects the canonical dangerous tool-call shapes (shell injection,
base64 payload, US SSN, 16-digit card) and returns None on benign
input. Per the design doc Phase A0 § "New backend modules", this
module ports a regex subset from the DefenseClaw Go-side rule-pack:
enough to satisfy the BDD acceptance criteria in story-mcp-03 plus
the common dangerous shapes; AI Defense is the authoritative
escalation when no cheap match fires.

All RuleHit results MUST carry `source="defenseclaw_regex"` so
Surface 4 dashboards correctly attribute cheap-pass hits to the
local rule-pack and not to AI Defense.
"""

from __future__ import annotations

import pytest
from splunkgate_judges.defenseclaw_backend import evaluate_tool_call

# --- 1: benign tool_call returns None -----------------------------------


async def test_benign_get_weather_returns_none() -> None:
    """Plain `get_weather(city="Toronto")` has no dangerous tokens → None."""
    hit = await evaluate_tool_call("get_weather", {"city": "Toronto"})
    assert hit is None


# --- 2: shell injection on shell_exec / rm -rf --------------------------


async def test_shell_exec_with_rm_rf_returns_shell_injection_hit() -> None:
    """`shell_exec` + `rm -rf /` arg → Shell Injection RuleHit."""
    hit = await evaluate_tool_call("shell_exec", {"cmd": "rm -rf /"})
    assert hit is not None
    assert hit.rule == "Shell Injection"
    assert hit.source == "defenseclaw_regex"
    assert hit.confidence == 1.0


# --- 3: base64 payload (≥ 100 alphanumeric chars) -----------------------


async def test_long_base64_payload_returns_base64_payload_hit() -> None:
    """≥ 100-char alphanumeric `[A-Za-z0-9+/=]` blob → Base64 Payload RuleHit."""
    payload = "A" * 60 + "B" * 60  # 120 chars, all base64 alphabet
    hit = await evaluate_tool_call("upload", {"data": payload})
    assert hit is not None
    assert hit.rule == "Base64 Payload"
    assert hit.source == "defenseclaw_regex"


# --- 4: US SSN pattern in tool_args -------------------------------------


async def test_ssn_in_tool_args_returns_pii_hit() -> None:
    """US SSN pattern `###-##-####` in any arg value → PII RuleHit."""
    hit = await evaluate_tool_call("send_email", {"to": "a@b.com", "body": "SSN: 123-45-6789"})
    assert hit is not None
    assert hit.rule == "PII"
    assert hit.source == "defenseclaw_regex"


# --- 5: 16-digit card-like in tool_args ---------------------------------


async def test_card_like_16_digit_returns_pci_hit() -> None:
    """16-digit card-shape `4242 4242 4242 4242` → PCI RuleHit."""
    hit = await evaluate_tool_call("charge", {"card": "4242 4242 4242 4242"})
    assert hit is not None
    assert hit.rule == "PCI"
    assert hit.source == "defenseclaw_regex"


# --- 6: mixed-key args, one key carrying PII ----------------------------


async def test_mixed_keys_with_one_ssn_value_caught() -> None:
    """Multiple keys, only one carrying SSN → still flagged PII.

    Guards against the obvious bug of only checking the first key, or
    only checking string values at the top level. The walker MUST
    inspect every value in the dict.
    """
    args: dict[str, object] = {
        "name": "Alice",
        "city": "Toronto",
        "subject": "Re: paperwork",
        "body": "Please confirm: SSN 987-65-4321 on file.",
    }
    hit = await evaluate_tool_call("send_email", args)
    assert hit is not None
    assert hit.rule == "PII"


# --- 7: nested dict walked recursively ----------------------------------


async def test_nested_dict_args_walked_for_ssn() -> None:
    """`{"outer": {"inner": "ssn..."}}` → SSN detected via recursive walk."""
    args: dict[str, object] = {"outer": {"inner": "Confidential: 555-12-3456"}}
    hit = await evaluate_tool_call("forward", args)
    assert hit is not None
    assert hit.rule == "PII"


# --- 8: confidence == 1.0 on every cheap-pass hit -----------------------


async def test_every_cheap_hit_has_confidence_one() -> None:
    """Deterministic regex matches → confidence == 1.0 always.

    DefenseClaw regex pack has no probabilistic scoring; either the
    pattern matched (1.0) or it didn't (None). Verifies that no
    accidental float scaling slipped in via copy-paste.
    """
    cases: list[tuple[str, dict[str, object]]] = [
        ("shell_exec", {"cmd": "rm -rf /home/user/data"}),
        ("send_email", {"body": "SSN 111-22-3333"}),
        ("charge", {"card": "5555 5555 5555 4444"}),
        ("upload", {"blob": "Z" * 150}),
    ]
    for tool_name, tool_args in cases:
        hit = await evaluate_tool_call(tool_name, tool_args)
        assert hit is not None, (tool_name, tool_args)
        assert hit.confidence == 1.0
        assert hit.source == "defenseclaw_regex"


# --- Bonus: nested list walked too -------------------------------------


async def test_nested_list_in_args_walked() -> None:
    """`{"items": ["foo", "ssn 123-45-6789"]}` → SSN detected in list element."""
    args: dict[str, object] = {"items": ["benign", "leak: 222-33-4444"]}
    hit = await evaluate_tool_call("batch", args)
    assert hit is not None
    assert hit.rule == "PII"


# --- Bonus: tool_name itself flagged for shell-shape names --------------


async def test_shell_exec_tool_name_without_explicit_rm_still_safe() -> None:
    """`shell_exec` + a benign arg returns None.

    The rule only fires when the dangerous SHAPE actually appears in
    the args — calling the rule on the tool_name alone would be a
    false-positive cliff (legitimate `shell_exec` calls happen daily
    in dev environments).
    """
    hit = await evaluate_tool_call("shell_exec", {"cmd": "ls -la"})
    # Benign — no rm -rf, no dangerous shape → no cheap hit.
    assert hit is None


# --- Bonus: regression — base64 length threshold strict ----------------


@pytest.mark.parametrize("length", [50, 80, 99])
async def test_short_alphanumeric_does_not_trip_base64(length: int) -> None:
    """Strings shorter than the 100-char threshold do NOT trip Base64 Payload.

    Without this guard, every UUID, every git SHA, every JWT header
    would false-positive. Keep the cliff sharp at 100 chars.
    """
    hit = await evaluate_tool_call("upload", {"data": "A" * length})
    assert hit is None

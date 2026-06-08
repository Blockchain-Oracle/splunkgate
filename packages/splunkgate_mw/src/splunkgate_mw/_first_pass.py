"""Cheap first-pass prompt-injection classifier + user-text extraction.

Re-exports `splunklib.ai.security.detect_injection` (9 verbatim regex
patterns at splunklib/ai/security.py:46-53) plus the helper for pulling
user-supplied content out of a splunklib message list.

Per ADR-010 in docs/architecture.md, the strategy is:
  1. Call detect_injection() as a cheap first-pass classifier (~us/call)
  2. If hit + escalate_on_first_pass_hit=True, escalate to Cisco AI Defense
     Inspection API "Prompt Injection" rule for the authoritative verdict
  3. Never replace the cheap path — composition not substitution
"""

from splunklib.ai.messages import (
    HumanMessage,
    ToolFailureResult,
    ToolMessage,
    ToolResult,
)
from splunklib.ai.security import detect_injection

__all__ = ["cheap_first_pass", "extract_user_text", "truncate_input"]

# DEFAULT_MAX_INPUT_LENGTH per splunklib.ai (see deep-read doc § "security module")
DEFAULT_MAX_INPUT_LENGTH = 10_000


def cheap_first_pass(text: str) -> bool:
    """Return True if any of splunklib.ai.security's 9 injection patterns match."""
    return bool(detect_injection(text))


def truncate_input(text: str, max_length: int = DEFAULT_MAX_INPUT_LENGTH) -> str:
    """Bound regex cost on adversarial mega-inputs (per deep-read § security)."""
    if len(text) <= max_length:
        return text
    return text[:max_length]


def extract_user_text(messages: list[object]) -> str:
    """Concatenate the latest HumanMessage + any ToolMessage content.

    Skips SystemMessage (operator-authored, trusted). For ToolMessage, the
    text comes from msg.result.content (ToolResult) or msg.result.error_message
    (ToolFailureResult).
    """
    parts: list[str] = []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            parts.append(str(msg.content))
            break
    for msg in messages:
        if isinstance(msg, ToolMessage):
            result = msg.result
            if isinstance(result, ToolResult):
                parts.append(result.content)
            elif isinstance(result, ToolFailureResult):
                parts.append(result.error_message)
    return "\n".join(parts)

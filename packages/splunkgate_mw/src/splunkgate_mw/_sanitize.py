"""Tool-arg sanitization helpers used by the MODIFY branch of SafetyToolMiddleware.

Patterns mirror the MCP twin's redactor map at
`packages/splunkgate_mcp/src/splunkgate_mcp/tools/judge_tool_call.py`
so Surface 1 and Surface 2 produce byte-identical sanitized output on
the same input. Rules without a v1 redactor (Base64 Payload, Shell
Injection) take the BLOCK branch upstream and never reach this code path,
so this map deliberately omits them.

Keep this module narrow — it owns the substring substitution only.
The verdict-assembly logic lives in `tool_middleware.py`.
"""

from __future__ import annotations

import re
from typing import Final

import structlog

__all__ = ["compose_sanitized", "is_supported_rule", "sanitize_args"]

_logger = structlog.get_logger(__name__)


_RULE_PATTERNS: Final[dict[str, list[re.Pattern[str]]]] = {
    "PII": [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ],
    "PCI": [
        re.compile(r"\b(?:\d[ -]*?){12,18}\d\b"),
    ],
}


def is_supported_rule(rule: str) -> bool:
    """Return True iff `compose_sanitized` has a v1 redactor for `rule`.

    Used by the verdict-assembly layer to detect AI Defense rules outside
    our redactor map (e.g., Code Detection, Harassment, Hate Speech,
    Profanity) BEFORE assembling MODIFY. Without this guard the loop
    in `_sanitize_string` would iterate zero times for the unmapped
    rule, return the input unchanged, and ship MODIFY with a byte-
    identical sanitized_args — the PR #117 silent-no-op shape.
    """
    return rule in _RULE_PATTERNS


def sanitize_args(tool_args: dict[str, object], rule: str) -> dict[str, object]:
    """Walk every value in tool_args, redacting string leaves for `rule`.

    EVERY input key is preserved — downstream agent code may depend on
    structural fields. Only string leaves are modified; non-string
    scalars (int / bool / float / None) pass through unchanged.
    """
    token = f"[REDACTED:{rule}]"
    return {k: _sanitize_value(v, rule, token) for k, v in tool_args.items()}


def compose_sanitized(
    tool_args: dict[str, object],
    rule_names: list[str],
) -> dict[str, object]:
    """Compose sanitization across multiple rule hits (PII then PCI etc.)."""
    out: dict[str, object] = dict(tool_args)
    for rule in rule_names:
        out = sanitize_args(out, rule)
    return out


def _sanitize_value(value: object, rule: str, token: str) -> object:
    if isinstance(value, str):
        return _sanitize_string(value, rule, token)
    if isinstance(value, dict):
        return {k: _sanitize_value(v, rule, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v, rule, token) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(v, rule, token) for v in value)
    # Non-string scalars (int / bool / float / None) pass silently — they
    # can't carry a regex-matchable PII / PCI substring. Anything ELSE
    # (set / frozenset / dataclass / custom object) is unusual on a
    # tool-call arg shape; WARN so operators can surface the drift.
    if not isinstance(value, int | float | bool | type(None)):
        _logger.warning(
            "sanitize.unhandled_container",
            rule=rule,
            value_type=type(value).__name__,
        )
    return value


def _sanitize_string(text: str, rule: str, token: str) -> str:
    redacted = text
    for pattern in _RULE_PATTERNS.get(rule, []):
        redacted = pattern.sub(token, redacted)
    return redacted

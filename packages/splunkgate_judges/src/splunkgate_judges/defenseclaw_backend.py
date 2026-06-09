"""DefenseClaw regex rule-pack — cheap first-pass classifier for tool-call args.

Per docs/architecture.md ADR-013a addendum + design doc Phase A0 §"New
backend modules", this module ports a regex subset from the DefenseClaw
Go-side rule-pack: enough to catch the BDD test cases + the common
dangerous patterns. AI Defense is the authoritative escalation when this
returns None (no cheap match) but the input still looks ambiguous.

API:
    async def evaluate_tool_call(
        tool_name: str, tool_args: dict[str, object]
    ) -> RuleHit | None

Returns a `RuleHit(rule=..., confidence=1.0, source="defenseclaw_regex")`
on match, or None if the cheap path is clean. NEVER returns a Verdict —
the calling tool builds the Verdict.

The walker descends nested dicts AND nested lists so a payload like
`{"outer": {"inner": "...ssn..."}}` or `{"items": [...]}` is still
inspected. Strings are the only leaf type we evaluate; other scalar
types (int, bool, float) are skipped — a JSON int can't carry a
shell-injection or SSN substring.

Patterns covered in v1:
  - Shell Injection: rm -rf / dd if=/ / curl … | sh — matched in arg values
    when the tool_name itself smells like a command runner.
  - Base64 Payload: ≥ 100 contiguous chars from `[A-Za-z0-9+/=]`. Sharp
    threshold (100) keeps UUIDs (32) and JWT headers (~80) out.
  - PII: US SSN `###-##-####`. (Email/phone redactors live downstream in
    check_output_leak.py's `_REDACTION_PATTERNS`; the defenseclaw cheap
    path focuses on the SSN signal which is both common and unambiguous.)
  - PCI: 16-digit card-shape (space/dash separated allowed, 13-19 digits).

Priority order (first hit wins): Shell Injection → PCI → PII → Base64.
Shell Injection is the highest-severity catastrophic shape (it executes
on the host) so it takes precedence. PCI/PII are ordered before Base64
because they carry more semantic weight in the rule-pack — Base64 is the
weakest signal (could be a legitimate file upload).
"""

from __future__ import annotations

import re
from typing import Final

from splunkgate_core.verdict import RuleHit

# Tool-name shapes that historically appear in agentic shell-runner tools.
# We use this set as the gate for the Shell Injection rule: matching a
# `rm -rf` shape inside an arg value of `get_weather` is not actually a
# shell injection (it's just a string); matching it inside `shell_exec`
# IS one. Keeps the false-positive rate low on legitimate text-handling
# tools that happen to mention shell commands.
_SHELL_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "shell_exec",
        "shell",
        "exec",
        "command",
        "bash",
        "sh",
        "run_command",
        "system",
    }
)

# Shell-injection shapes. We do NOT try to enumerate every dangerous
# command — just the canonical destructive patterns + the curl-to-shell
# pipe which is the classic remote-code-execution path.
_SHELL_INJECTION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\brm\s+-[rRf]+\b"),  # rm -rf / rm -Rf / rm -fr
    re.compile(r"\bdd\s+if=/"),  # dd if=/dev/zero of=...
    re.compile(r"\bcurl\b[^|;]*\|\s*(?:sh|bash)\b"),  # curl ... | sh
    re.compile(r"\bwget\b[^|;]*\|\s*(?:sh|bash)\b"),  # wget ... | sh
    re.compile(r":\(\)\s*\{.*:\|:&"),  # fork-bomb
    re.compile(r">\s*/dev/sd[a-z]"),  # > /dev/sda
)

# Base64 payload: ≥ 100 contiguous chars from the standard alphabet. Used
# as a smell test for `data:` / `payload:` arg keys that carry encoded
# binaries — useful for catching exfiltration attempts via tool-call args.
# Sharp 100-char threshold keeps UUIDs / JWT headers from tripping it.
_BASE64_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9+/=]{100,}")

# US SSN: ###-##-####. Same shape as check_output_leak.py's PII redactor;
# duplicated here intentionally — the cheap-pass module owns the cheap
# detection, the leak-tool owns the redaction substitution, neither
# module should import the other (no cross-tool surface coupling).
_SSN_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# 16-digit card-shape, optionally space-or-dash separated. AI Defense
# upstream would Luhn-validate; the cheap path just matches the SHAPE so
# the calling tool can decide whether to MODIFY / BLOCK.
_CARD_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:\d[ -]*?){12,18}\d\b")


def _is_shell_tool(tool_name: str) -> bool:
    """Return True if tool_name matches the known shell-runner shapes."""
    return tool_name.lower() in _SHELL_TOOL_NAMES


def _iter_strings(value: object) -> list[str]:
    """Walk a nested structure and return every string leaf.

    Dicts + lists + tuples descend recursively. Other scalar types
    (int, bool, float, None) are skipped because they can't carry a
    regex-matchable dangerous substring. Sets are walked as iterables
    too — defensive against agents that pass arbitrary JSON-encoded
    structures (though set isn't strictly JSON-native).

    Bounded recursion depth via explicit stack — protects against
    pathological circular structures that an adversarial caller might
    construct to DoS the matcher.
    """
    out: list[str] = []
    stack: list[object] = [value]
    seen: set[int] = set()
    max_depth = 1000  # explicit cap so a malicious nested struct can't hang us
    iterations = 0
    while stack and iterations < max_depth:
        iterations += 1
        item = stack.pop()
        item_id = id(item)
        if item_id in seen:
            continue
        if isinstance(item, (dict, list, tuple, set)):
            seen.add(item_id)
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set)):
            stack.extend(item)
        # other types skipped silently — int / bool / float / None
    return out


def _match_shell_injection(tool_name: str, strings: list[str]) -> bool:
    """True iff tool_name smells like a shell runner AND an arg looks injected."""
    if not _is_shell_tool(tool_name):
        return False
    for s in strings:
        for pattern in _SHELL_INJECTION_PATTERNS:
            if pattern.search(s):
                return True
    return False


def _match_any(pattern: re.Pattern[str], strings: list[str]) -> bool:
    """Return True iff `pattern` matches any string in `strings`."""
    return any(pattern.search(s) for s in strings)


async def evaluate_tool_call(
    tool_name: str,
    tool_args: dict[str, object],
) -> RuleHit | None:
    """Run the regex rule-pack subset over a tool invocation.

    Returns the first matching RuleHit at confidence 1.0 (deterministic
    regex — match or no match), or None if every pattern was clean.

    Priority order: Shell Injection → PCI → PII → Base64. Shell
    Injection takes precedence because it executes on the host;
    PCI/PII are the most semantically heavy data-leak shapes; Base64
    is the weakest signal (often legitimate).

    The function is `async` to match the interface every other backend
    in `splunkgate_judges` exposes (consistency at the call site) —
    internally it's CPU-bound regex, no I/O, so it never awaits.
    """
    strings = _iter_strings(tool_args)

    if _match_shell_injection(tool_name, strings):
        return RuleHit(rule="Shell Injection", confidence=1.0, source="defenseclaw_regex")

    if _match_any(_CARD_PATTERN, strings):
        return RuleHit(rule="PCI", confidence=1.0, source="defenseclaw_regex")

    if _match_any(_SSN_PATTERN, strings):
        return RuleHit(rule="PII", confidence=1.0, source="defenseclaw_regex")

    if _match_any(_BASE64_PATTERN, strings):
        return RuleHit(rule="Base64 Payload", confidence=1.0, source="defenseclaw_regex")

    return None

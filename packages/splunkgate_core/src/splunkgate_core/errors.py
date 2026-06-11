"""SplunkGate error model — single hierarchy under SplunkGateError.

Per architecture.md § "Coding standards" soft rules: "All errors raised
are subclasses of splunkgate_core.errors.SplunkGateError." This module establishes
the hierarchy; downstream stories enforce it by always raising one of
these classes.

Chained causes use Python's built-in __cause__ via `raise NewErr(...) from e`.
Do not add a custom `cause` constructor arg.
"""

from uuid import UUID


class SplunkGateError(Exception):
    """Base for every SplunkGate error.

    Carries an optional trace_id so the failing request can be correlated
    against its Verdict, OTel event, and structured log lines.
    """

    def __init__(self, message: str, *, trace_id: UUID | None = None) -> None:
        """Initialize with a message and optional trace_id for correlation."""
        super().__init__(message)
        self.trace_id = trace_id


class JudgmentError(SplunkGateError):
    """Raised when a judgment-layer client fails.

    Examples: AI Defense API returned 5xx, DefenseClaw regex pack failed
    to load, Foundation-Sec SPL explainer raised at parse-time.
    """


class ConfigError(SplunkGateError):
    """Raised on invalid SplunkGate config.

    Examples: missing SPLUNKGATE_AI_DEFENSE_API_KEY env var, profile not in
    {financial_services, healthcare, public_sector}, malformed YAML.
    """


class NetworkError(SplunkGateError):
    """Raised on HTTP/network failure.

    Wraps httpx exceptions when no more specific judgment-layer or
    config-layer cause applies. Always chained via `raise ... from e`
    so the underlying httpx exception is preserved in __cause__.
    """


class ValidationError(SplunkGateError):
    """Raised when input violates a structural validation rule.

    Used by `splunkgate_judge_tool_call` for the 64 KB tool_args cap +
    other bounded-size validations in mcp-03..05 + future mw work.
    Subclasses `SplunkGateError` so it propagates through MCP's lowlevel
    handler as `isError: true` per the in-band error pattern.
    """


class ModelInputBlockedBySplunkGate(SplunkGateError):  # noqa: N818 — name locked by story-mw-03 + architecture.md
    """Raised by SafetyModelMiddleware when pre-inference scan returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The model was NEVER invoked.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Model input blocked by SplunkGate: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict


class ModelOutputBlockedBySplunkGate(SplunkGateError):  # noqa: N818 — name locked by story-mw-04 + architecture.md
    """Raised by SafetyModelMiddleware when post-inference scan returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The model WAS invoked but its output never
    reaches the caller or any downstream tool.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Model output blocked by SplunkGate: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict


class ToolBlockedBySplunkGate(SplunkGateError):  # noqa: N818 — name locked by story-mw-02 + architecture.md
    """Raised by SafetyToolMiddleware when tool-call judgement returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The downstream tool handler was NEVER invoked
    — the agent loop unwinds with the typed exception and downstream
    callers can inspect `e.verdict`.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Tool call blocked by SplunkGate: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict


class UnknownProfile(SplunkGateError):  # noqa: N818 — name locked by story-mw-07
    """Raised by `resolve_profile()` when the caller passed an unknown profile name.

    `splunkgate_mw.resolve_profile("nonsense")` raises this to surface a
    typo at construction time rather than silently falling back to the
    default profile and shipping the wrong rule chain to a regulated
    workload. Carries the offending name + the live valid-name tuple so
    callers can report the actual canonical set rather than relying on a
    stale list baked into this module.
    """

    def __init__(self, name: str, *, valid: tuple[str, ...] = ()) -> None:
        """Wrap the offending profile name; message lists the valid set."""
        super().__init__(f"Unknown profile {name!r} — valid: {valid}")
        self.name = name
        self.valid = valid


class SubagentBlockedBySplunkGate(SplunkGateError):  # noqa: N818 — name locked by story-mw-05 + architecture.md
    """Raised by SafetySubagentMiddleware when subagent-call judgement returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The downstream subagent handler was NEVER
    invoked — the parent agent's loop unwinds with the typed exception
    and downstream callers can inspect `e.verdict`. Surface is
    `mw_subagent`.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Subagent call blocked by SplunkGate: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict

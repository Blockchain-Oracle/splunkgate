"""Aegis error model — single hierarchy under AegisError.

Per architecture.md § "Coding standards" soft rules: "All errors raised
are subclasses of aegis_core.errors.AegisError." This module establishes
the hierarchy; downstream stories enforce it by always raising one of
these classes.

Chained causes use Python's built-in __cause__ via `raise NewErr(...) from e`.
Do not add a custom `cause` constructor arg.
"""

from uuid import UUID


class AegisError(Exception):
    """Base for every Aegis error.

    Carries an optional trace_id so the failing request can be correlated
    against its Verdict, OTel event, and structured log lines.
    """

    def __init__(self, message: str, *, trace_id: UUID | None = None) -> None:
        """Initialize with a message and optional trace_id for correlation."""
        super().__init__(message)
        self.trace_id = trace_id


class JudgmentError(AegisError):
    """Raised when a judgment-layer client fails.

    Examples: AI Defense API returned 5xx, DefenseClaw regex pack failed
    to load, Foundation-Sec SPL explainer raised at parse-time.
    """


class ConfigError(AegisError):
    """Raised on invalid Aegis config.

    Examples: missing AEGIS_AI_DEFENSE_API_KEY env var, profile not in
    {financial_services, healthcare, public_sector}, malformed YAML.
    """


class NetworkError(AegisError):
    """Raised on HTTP/network failure.

    Wraps httpx exceptions when no more specific judgment-layer or
    config-layer cause applies. Always chained via `raise ... from e`
    so the underlying httpx exception is preserved in __cause__.
    """


class ModelInputBlockedByAegis(AegisError):  # noqa: N818 — name locked by story-mw-03 + architecture.md
    """Raised by SafetyModelMiddleware when pre-inference scan returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The model was NEVER invoked.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Model input blocked by Aegis: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict


class ModelOutputBlockedByAegis(AegisError):  # noqa: N818 — name locked by story-mw-04 + architecture.md
    """Raised by SafetyModelMiddleware when post-inference scan returns BLOCK.

    Carries the Verdict that caused the block so callers can inspect rules,
    severity, and explanation. The model WAS invoked but its output never
    reaches the caller or any downstream tool.
    """

    def __init__(self, verdict: object) -> None:
        """Wrap the blocking verdict; message is built from verdict.explanation."""
        message = f"Model output blocked by Aegis: {verdict!r}"
        super().__init__(message)
        self.verdict = verdict

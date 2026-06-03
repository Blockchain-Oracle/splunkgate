"""Aegis structlog configuration + stable key conventions.

Every surface calls `from aegis_core.logging import get_logger` and gets a
pre-configured BoundLogger that:

1. Renders JSON in prod (HEC-ingestible by Splunk) and console-pretty in dev
   (configurable via AEGIS_LOG_FORMAT={json|console} env var or `dev_mode`
   kwarg to `configure_logging()`)
2. Emits the stable Aegis key set on every record:
   - `event`     human-readable event name
   - `verdict`   "ALLOW" | "BLOCK" | "MODIFY" | "REVIEW"
   - `severity`  "NONE_SEVERITY" | "LOW" | "MEDIUM" | "HIGH"
   - `trace_id`  str(UUID) — auto-injected from aegis_core.trace.current_trace_id()
3. Auto-injects `trace_id` from the active `trace_context()` so callers
   don't have to thread it manually through every log line

Per architecture.md "Banned patterns": writing to stdout via builtin output
functions for logs is banned. Use this module's logger or structlog's
BoundLogger directly.
"""

import logging as stdlib_logging
import os
import sys
from typing import Literal

import structlog

from aegis_core.trace import current_trace_id

LogKey = Literal[
    "event",
    "verdict",
    "severity",
    "trace_id",
    "surface",
    "rule",
    "confidence",
    "latency_ms",
    "agent_id",
    "model_name",
]
"""The stable set of structured-log keys Aegis emits.

Documentation-only contract: structlog's `bind()` is typed `**kw: Any` so
mypy won't enforce key spelling automatically. Surface code that wants
the check should type-annotate intermediate variables as `LogKey` before
passing — e.g. `key: LogKey = "verdict"; log.bind(**{key: "BLOCK"})`."""


def _trace_id_processor(
    _logger: object,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Auto-inject trace_id from the active trace_context, if any."""
    tid = current_trace_id()
    if tid is not None:
        event_dict["trace_id"] = str(tid)
    return event_dict


def _resolve_dev_mode(*, dev_mode_kwarg: bool | None) -> bool:
    """Resolve dev/prod mode from explicit kwarg, env var, then TTY detection."""
    if dev_mode_kwarg is not None:
        return dev_mode_kwarg
    env = os.environ.get("AEGIS_LOG_FORMAT", "").strip().lower()
    if env == "json":
        return False
    if env == "console":
        return True
    return sys.stderr.isatty()


def configure_logging(*, dev_mode: bool | None = None) -> None:
    """Wire structlog's processor chain + renderer.

    Resolution order for dev/prod selection:
      1. Explicit `dev_mode` kwarg (True/False)
      2. AEGIS_LOG_FORMAT env var ("json" → prod, "console" → dev)
      3. sys.stderr.isatty() — True (interactive) → dev, False (CI/prod) → prod
    """
    is_dev = _resolve_dev_mode(dev_mode_kwarg=dev_mode)
    renderer: structlog.types.Processor
    renderer = structlog.dev.ConsoleRenderer() if is_dev else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _trace_id_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a BoundLogger; safe to call before configure_logging()."""
    # structlog.get_logger returns BoundLoggerLazyProxy typed as Any —
    # cast to BoundLogger for the public API. The proxy resolves to a
    # real native BoundLogger on first call (not stdlib.BoundLogger —
    # this module configures the native wrapper via make_filtering_bound_logger).
    return structlog.get_logger(name)  # type: ignore[no-any-return]

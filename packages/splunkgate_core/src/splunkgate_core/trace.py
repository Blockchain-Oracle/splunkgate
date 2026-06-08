"""trace_id propagation — ContextVar-based, sync + async safe.

A single UUID threads through Verdict, OTel event attrs, SplunkGateError instances,
and structlog records so one logical request is correlatable end-to-end.
asyncio preserves ContextVar values across `await` and gives each task its
own contextvars copy — exactly what we want for per-request isolation.

Separate from OTel's 128-bit span trace_id; both can coexist (surface
stories emit `splunkgate.trace_id` as an OTel event attr).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID, uuid4

_trace_id_var: ContextVar[UUID | None] = ContextVar("splunkgate_trace_id", default=None)


def new_trace_id() -> UUID:
    """Mint a fresh UUID for a logical SplunkGate request."""
    return uuid4()


def current_trace_id() -> UUID | None:
    """Return the trace_id active in the current contextvars context, or None."""
    return _trace_id_var.get()


def set_trace_id(trace_id: UUID) -> None:
    """Set the trace_id in the current contextvars context (no reset).

    Prefer trace_context() — it auto-resets on exit. Use this only at request
    entry points where there is no enclosing context manager.
    """
    _trace_id_var.set(trace_id)


@contextmanager
def trace_context(trace_id: UUID) -> Iterator[None]:
    """Bind trace_id to the current contextvars context for the duration of the with-block.

    Works for both sync `with` and inside `async def` — asyncio preserves
    ContextVar bindings across `await` boundaries.
    """
    token = _trace_id_var.set(trace_id)
    try:
        yield
    finally:
        _trace_id_var.reset(token)

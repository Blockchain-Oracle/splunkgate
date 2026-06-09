"""Test session config — shared OTel TracerProvider + InMemorySpanExporter.

Mirrors `packages/splunkgate_core/tests/conftest.py`: OTel's
`set_tracer_provider()` is process-global and set-once. Each test
package that needs to capture spans must register its provider exactly
once and share the resulting exporter across its test modules. Without
this, the `score_prompt_injection` tool's `emit_verdict_event` call lands
in a NonRecordingSpan and silently never reaches the in-memory exporter.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# If splunkgate_core/tests ran first in the same pytest session it
# already installed a TracerProvider. `get_tracer_provider()` returns
# the active one; we only register a new provider when none is set
# (the default ProxyTracerProvider has class name "ProxyTracerProvider").
_existing = trace.get_tracer_provider()
if type(_existing).__name__ == "ProxyTracerProvider":
    SHARED_EXPORTER: InMemorySpanExporter = InMemorySpanExporter()
    _PROVIDER = TracerProvider()
    _PROVIDER.add_span_processor(SimpleSpanProcessor(SHARED_EXPORTER))
    trace.set_tracer_provider(_PROVIDER)
else:
    # Reuse the existing provider; install a fresh SimpleSpanProcessor
    # whose exporter we own so our tests have a clean view.
    SHARED_EXPORTER = InMemorySpanExporter()
    _existing.add_span_processor(SimpleSpanProcessor(SHARED_EXPORTER))  # type: ignore[attr-defined]


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
    """Yield the shared InMemorySpanExporter, clearing before each test."""
    SHARED_EXPORTER.clear()
    return SHARED_EXPORTER

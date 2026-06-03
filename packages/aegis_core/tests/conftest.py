"""Test session config — hypothesis profile + shared OTel TracerProvider.

OTel's set_tracer_provider() is process-global and set-once. Two test
modules that each call it independently produce a silent no-op on the
second module's setup (the first wins), causing the second module's
InMemorySpanExporter to never receive any spans. Centralizing the
provider + exporter here makes both test_otel.py and
test_otel_hec_exporter.py share one provider with one exporter.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, settings
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

settings.register_profile(
    "ci",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")

# Module-level shared TracerProvider + InMemorySpanExporter.
SHARED_EXPORTER = InMemorySpanExporter()
_SHARED_PROVIDER = TracerProvider()
_SHARED_PROVIDER.add_span_processor(SimpleSpanProcessor(SHARED_EXPORTER))
trace.set_tracer_provider(_SHARED_PROVIDER)


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
    """Yield the shared InMemorySpanExporter, clearing before each test."""
    SHARED_EXPORTER.clear()
    return SHARED_EXPORTER

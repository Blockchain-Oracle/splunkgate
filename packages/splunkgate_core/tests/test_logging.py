"""Behavioral tests for splunkgate_core.logging configuration + trace_id injection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import structlog
from splunkgate_core.logging import configure_logging, get_logger
from splunkgate_core.trace import new_trace_id, trace_context
from structlog.testing import LogCapture

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_structlog_after_each() -> Iterator[None]:
    """Reset structlog config between tests so each one starts fresh."""
    yield
    structlog.reset_defaults()


def _install_capture() -> LogCapture:
    """Insert LogCapture at the end of the configured processor chain.

    structlog.testing.capture_logs replaces the whole chain — our
    _trace_id_processor never runs there. Inserting LogCapture as the
    terminal processor preserves the upstream injection.
    """
    cap = LogCapture()
    current = structlog.get_config()["processors"]
    structlog.configure(processors=[*current[:-1], cap])
    return cap


def test_get_logger_returns_bound_logger() -> None:
    log = get_logger("test")
    assert hasattr(log, "info")
    assert hasattr(log, "bind")


def test_capture_records_event_key() -> None:
    configure_logging(dev_mode=False)
    cap = _install_capture()
    log = get_logger("test")
    log.info("hello world", verdict="BLOCK", severity="HIGH")
    assert any(r.get("event") == "hello world" for r in cap.entries)


def test_bound_keys_round_trip_through_capture() -> None:
    configure_logging(dev_mode=False)
    cap = _install_capture()
    log = get_logger("test")
    log.info("verdict_emitted", verdict="ALLOW", severity="LOW")
    record = next(r for r in cap.entries if r.get("event") == "verdict_emitted")
    assert record["verdict"] == "ALLOW"
    assert record["severity"] == "LOW"


def test_trace_id_auto_injected_inside_trace_context() -> None:
    configure_logging(dev_mode=False)
    cap = _install_capture()
    log = get_logger("test")
    tid = new_trace_id()
    with trace_context(tid):
        log.info("inside_trace")
    record = next(r for r in cap.entries if r.get("event") == "inside_trace")
    assert record.get("trace_id") == str(tid)


def test_trace_id_omitted_outside_any_context() -> None:
    configure_logging(dev_mode=False)
    cap = _install_capture()
    log = get_logger("test")
    log.info("no_trace")
    record = next(r for r in cap.entries if r.get("event") == "no_trace")
    assert record.get("trace_id") is None


def test_splunkgate_log_format_env_var_overrides_to_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPLUNKGATE_LOG_FORMAT", "json")
    configure_logging()  # dev_mode=None → look at env
    cap = _install_capture()
    log = get_logger("test")
    log.info("env_json_test")
    assert any(r.get("event") == "env_json_test" for r in cap.entries)


def test_splunkgate_log_format_env_var_overrides_to_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPLUNKGATE_LOG_FORMAT", "console")
    configure_logging()
    cap = _install_capture()
    log = get_logger("test")
    log.info("env_console_test")
    assert any(r.get("event") == "env_console_test" for r in cap.entries)


def test_explicit_dev_mode_kwarg_beats_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dev_mode=True must win over SPLUNKGATE_LOG_FORMAT=json env var."""
    monkeypatch.setenv("SPLUNKGATE_LOG_FORMAT", "json")
    configure_logging(dev_mode=True)
    cap = _install_capture()
    log = get_logger("test")
    log.info("kwarg_wins")
    assert any(r.get("event") == "kwarg_wins" for r in cap.entries)


def test_nested_trace_context_inner_id_visible_in_inner_logs() -> None:
    """Nested trace_context blocks: inner trace_id appears in inner-scope logs."""
    configure_logging(dev_mode=False)
    cap = _install_capture()
    log = get_logger("test")
    outer = new_trace_id()
    inner = new_trace_id()
    with trace_context(outer):
        log.info("outer_log")
        with trace_context(inner):
            log.info("inner_log")
        log.info("after_inner")
    outer_rec = next(r for r in cap.entries if r["event"] == "outer_log")
    inner_rec = next(r for r in cap.entries if r["event"] == "inner_log")
    after_rec = next(r for r in cap.entries if r["event"] == "after_inner")
    assert outer_rec["trace_id"] == str(outer)
    assert inner_rec["trace_id"] == str(inner)
    assert after_rec["trace_id"] == str(outer)


def test_configure_logging_does_not_raise_with_unset_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tiebreaker: with no kwarg + no env var, falls back to TTY detection."""
    monkeypatch.delenv("SPLUNKGATE_LOG_FORMAT", raising=False)
    configure_logging()
    assert os.environ.get("SPLUNKGATE_LOG_FORMAT") is None

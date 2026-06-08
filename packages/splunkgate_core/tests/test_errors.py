"""Behavioral tests for the splunkgate_core.errors hierarchy."""

from uuid import uuid4

import pytest
from splunkgate_core.errors import ConfigError, JudgmentError, NetworkError, SplunkGateError


def test_judgment_error_is_splunkgate_error() -> None:
    assert issubclass(JudgmentError, SplunkGateError)


def test_config_error_is_splunkgate_error() -> None:
    assert issubclass(ConfigError, SplunkGateError)


def test_network_error_is_splunkgate_error() -> None:
    assert issubclass(NetworkError, SplunkGateError)


def test_splunkgate_error_accepts_trace_id_kwarg() -> None:
    tid = uuid4()
    err = SplunkGateError("boom", trace_id=tid)
    assert err.trace_id == tid


def test_splunkgate_error_trace_id_defaults_to_none() -> None:
    err = SplunkGateError("boom")
    assert err.trace_id is None


def _raise_chained(original: Exception) -> None:
    """Helper isolating the chained-raise so PT012 sees a single statement."""
    msg = "wrapped"
    raise JudgmentError(msg, trace_id=uuid4()) from original


def test_splunkgate_error_preserves_cause_via_raise_from() -> None:
    """Chained cause uses Python's __cause__; no custom cause constructor arg."""
    original = ValueError("root cause")
    with pytest.raises(JudgmentError) as exc_info:
        _raise_chained(original)
    assert exc_info.value.__cause__ is original


def test_subclasses_carry_trace_id_inherited() -> None:
    tid = uuid4()
    for cls in (JudgmentError, ConfigError, NetworkError):
        err = cls("x", trace_id=tid)
        assert err.trace_id == tid


def test_message_preserved_via_str() -> None:
    err = NetworkError("connection refused")
    assert str(err) == "connection refused"


def test_can_be_caught_via_base_class() -> None:
    """try/except SplunkGateError must catch every concrete subclass."""
    msg = "x"
    for cls in (JudgmentError, ConfigError, NetworkError):
        with pytest.raises(SplunkGateError):
            raise cls(msg)

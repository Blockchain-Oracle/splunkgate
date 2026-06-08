import splunkgate_mw


def test_version_present() -> None:
    assert splunkgate_mw.__version__ == "0.1.0"

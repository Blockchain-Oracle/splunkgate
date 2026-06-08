import splunkgate_core


def test_version_present() -> None:
    assert splunkgate_core.__version__ == "0.0.1"

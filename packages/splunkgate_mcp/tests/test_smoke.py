import splunkgate_mcp


def test_version_present() -> None:
    assert splunkgate_mcp.__version__ == "0.0.1"

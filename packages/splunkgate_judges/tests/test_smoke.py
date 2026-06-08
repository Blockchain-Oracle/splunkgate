import splunkgate_judges


def test_version_present() -> None:
    assert splunkgate_judges.__version__ == "0.1.0"

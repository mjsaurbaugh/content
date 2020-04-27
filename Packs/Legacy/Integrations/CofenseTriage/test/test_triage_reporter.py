import pytest

from ..triage_reporter import TriageReporter


class TestTriageReporter:
    def test_init(self, requests_mock, fixture_from_file):
        requests_mock.get(
            "https://some-triage-host/api/public/v1/reporters/5",
            text=fixture_from_file("individual_reporter_response.json"),
        )

        reporter = TriageReporter(5)

        assert reporter.attrs["email"] == "user387@cofense.com"

    def test_exists(self, requests_mock, fixture_from_file):
        requests_mock.get(
            "https://some-triage-host/api/public/v1/reporters/5",
            text=fixture_from_file("individual_reporter_response.json"),
        )
        requests_mock.get(
            "https://some-triage-host/api/public/v1/reporters/6", text="[]"
        )

        assert TriageReporter(5).exists() is True
        assert TriageReporter(6).exists() is False
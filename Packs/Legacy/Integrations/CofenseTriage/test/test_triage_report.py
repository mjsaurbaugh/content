import pytest

from ..triage_report import TriageReport


@pytest.fixture
def single_report_json(fixture_from_file):
    return fixture_from_file("single_report.json")


@pytest.fixture
def single_report_with_attachment_json(fixture_from_file):
    return fixture_from_file("single_report_with_attachment.json")


class TestTriageReport:
    def test_attrs(self, single_report_json):
        report = TriageReport.from_json(single_report_json)

        assert len(report.attrs) == 8
        assert report.id == "1"
        assert report.date == "2000-04-20T01:02:03.000000Z"

    def test_reporter(self, mocker, single_report_json):
        stubbed_triagereporter_init = mocker.patch(
            "CofenseTriage.triage_report.TriageReporter"
        )

        TriageReport.from_json(single_report_json).reporter

        stubbed_triagereporter_init.assert_called_once_with("reporter1")

    def test_attachment_none(self, single_report_json):
        report = TriageReport.from_json(single_report_json)

        assert report.attachment == None

    def test_attachment_present(self, mocker, single_report_with_attachment_json):
        mocker.patch(
            "CofenseTriage.triage_report.fileResult",
            lambda **_kwargs: {
                "FileID": "file_result_id",
                "FileName": "file_result_name",
            },
        )

        report = TriageReport.from_json(single_report_with_attachment_json)
        attachment = report.attachment

        assert attachment == {"path": "file_result_id", "name": "file_result_name"}
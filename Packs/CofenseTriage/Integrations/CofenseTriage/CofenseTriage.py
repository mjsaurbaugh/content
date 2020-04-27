import demistomock as demisto
from CommonServerPython import *

from typing import Any, List, Dict
from io import BytesIO
from PIL import Image

from . import triage_instance
triage_instance.init() 
from .triage_instance import TRIAGE_INSTANCE
from .triage_report import TriageReport
from .triage_reporter import TriageReporter

DEFAULT_TIME_RANGE = '7 days'  # type: str
TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'  # type: str

TERSE_FIELDS = [
    'id',
    'cluster_id',
    'reporter_id',
    'location',
    'created_at',
    'reported_at',
    'report_subject',
    'report_body',
    'md5',
    'sha256',
    'category_id',
    'match_priority',
    'tags',
    'email_attachments',
]


def snake_to_camel_keys(snake_list: List[Dict]) -> List[Dict]:
    def snake_to_camel(snake_str) -> str:
        if snake_str == 'id':
            return 'ID'
        components = snake_str.split('_')
        return ''.join(x.title() for x in components)

    return [
        {snake_to_camel(k): v for k, v in snake_d.items()} for snake_d in snake_list
    ]


def split_snake(string: str) -> str:
    return string.replace("_", " ").title()


def test_function() -> None:
    try:
        response = TRIAGE_INSTANCE.request("processed_reports")

        if response:
            # test fetching mechanism
            if demisto.params().get('isFetch'):
                fetch_reports()

            demisto.results('ok')
        else:
            return_error(
                "API call to Cofense Triage failed. Please check Server URL, or authentication "
                "related parameters.Status Code: {response.status_code} Reason: {response.reason}"
                f" [{response.status_code}] - {response.reason}"
            )
    except Exception as ex:
        demisto.debug(str(ex))
        return_error(repr(ex))


def fetch_reports() -> None:
    """Fetch up to `max_reports` reports since the last time the command was run. TODO date_range"""
    start_date, _ = parse_date_range(
        demisto.getParam('date_range'), date_format=TIME_FORMAT
    )
    max_fetch = int(demisto.getParam('max_fetch'))

    triage_response = TRIAGE_INSTANCE.request(
        "processed_reports",
        params={
            "category_id": demisto.getParam("category_id"),
            "match_priority": demisto.getParam("match_priority"),
            "tags": demisto.getParam("tags"),
            "start_date": start_date,
        },
    )

    already_fetched = set(demisto.getLastRun().get('reports_fetched', '[]'))

    triage_reports = [
        TriageReport(report)
        for report in triage_response
        if report["id"] not in already_fetched
    ]

    incidents = []
    for report in triage_reports:
        incident = {
            'name': f"cofense triage report {report.id}: {report.category_name}",
            'occurred': report.date,
            'rawJSON': report.to_json(),
            'severity': report.severity,
        }

        if report.attachment:
            incident['attachment'] = report.attachment

        incidents.append(incident)
        already_fetched.add(report.id)
        if len(incidents) >= max_fetch:
            break

    demisto.incidents(incidents)
    demisto.setLastRun({'reports_fetched': already_fetched})  # TODO JSON?


def search_reports_command() -> None:
    # arguments importing
    subject = demisto.getArg('subject')  # type: str
    url = demisto.getArg('url')  # type: str
    file_hash = demisto.getArg('file_hash')  # type: str
    reported_at, _ = parse_date_range(demisto.args().get('reported_at', DEFAULT_TIME_RANGE))
    created_at, _ = parse_date_range(demisto.args().get('created_at', DEFAULT_TIME_RANGE))
    reporter = demisto.getArg('reporter')  # type: str
    max_matches = int(demisto.getArg('max_matches'))  # type: int
    verbose = demisto.getArg('verbose') == "true"

    # running the API command
    results = search_reports(subject, url, file_hash, reported_at, created_at, reporter, verbose, max_matches)

    # parsing outputs
    if results:
        ec = {'Cofense.Report(val.ID && val.ID == obj.ID)': snake_to_camel_keys(results)}
        hr = tableToMarkdown("Reports:", results, headerTransform=split_snake, removeNull=True)

        demisto.results({
            'Type': entryTypes['note'],
            'ContentsFormat': formats['markdown'],
            'Contents': results if results else "no results were found",
            'HumanReadable': hr,
            'EntryContext': ec
        })
    else:
        return_outputs("no results were found.", {})


def search_reports(subject=None, url=None, file_hash=None, reported_at=None, created_at=None, reporter=None,
                   verbose=False, max_matches=30) -> list:
    params = {'start_date': datetime.strftime(reported_at, TIME_FORMAT)}
    reports = TRIAGE_INSTANCE.request("processed_reports", params=params)

    if not isinstance(reports, list):
        reports = [reports]

    reporters = []  # type: list
    if reporter:
        reporters = get_all_reporters(time_frame=min(reported_at, created_at))

    matches = []

    for report in reports:
        if subject and subject != report.get('report_subject'):
            # TODO do we really want to do exact string match here? not case-insensitive substring?
            continue
        if url and url != report.get('url'):
            continue
        if created_at and 'created_at' in report and created_at >= datetime.strptime(report['created_at'], TIME_FORMAT):
            continue
        if file_hash and file_hash != report.get('md5') and file_hash != report.get('sha256'):
            continue
        if reporter and int(reporter) != report.get('reporter_id') and reporter not in reporters:
            continue

        if not verbose:
            # extract only relevant fields
            report = {key: report[key] for key in report.keys() & TERSE_FIELDS}

        matches.append(report)
        if len(matches) >= max_matches:
            break

    return matches


def get_all_reporters(time_frame) -> list:
    res = TRIAGE_INSTANCE.request("reporters", params={'start_date': time_frame})
    if not isinstance(res, list):
        res = [res]
    reporters = [reporter.get('email') for reporter in res]

    return reporters


def get_reporter_command() -> None:
    reporter_id = demisto.getArg('reporter_id')

    reporter = TriageReporter(reporter_id)

    if not reporter.exists():
        return return_outputs(
            readable_output="Could not find reporter with matching ID",
            outputs=reporter_id,
        )

    demisto.results(
        {
            "Type": entryTypes["note"],
            "ContentsFormat": formats["markdown"],
            "Contents": reporter.attrs,
            "HumanReadable": tableToMarkdown(
                "Reporter Results:",
                reporter.attrs,
                headerTransform=split_snake,
                removeNull=True
            ),
        }
    )


def get_attachment_command() -> None:
    # arguments importing
    attachment_id = demisto.getArg('attachment_id')  # type: str
    file_name = demisto.getArg('file_name') or attachment_id  # type: str

    # running the command
    res = get_attachment(attachment_id)

    # parsing outputs
    context_data = {'ID': attachment_id}
    demisto.results(fileResult(file_name, res.content))
    demisto.results({
        'Type': entryTypes['note'],
        'ContentsFormat': formats['markdown'],
        'Contents': '',
        'HumanReadable': '',
        'EntryContext': {'Cofense.Attachment(val.ID == obj.ID)': context_data}
    })


def get_attachment(attachment_id):
    response = TRIAGE_INSTANCE.request(f'attachment/{attachment_id}', raw_response=True)
    if not response.ok:
        return_error(f'Call to Cofense Triage failed [{response.status_code}]')
    else:
        return response


def get_report_by_id_command() -> None:
    report_id = int(demisto.getArg('report_id'))  # type: int
    verbose = demisto.getArg('verbose') == "true"

    report = TriageReport(TRIAGE_INSTANCE.request(f"reports/{report_id}"))
        # TODO new classmethod on TriageReport that makes the TRIAGE_INSTANCE call
    res = report.attrs #TODO

    if not verbose:
        # extract only relevant fields
        res = {k: res[k] for k in res.keys() & TERSE_FIELDS}

    # get the report body, and create html file if necessary
    if res:
        parse_report_body(res)
    #FIXME    res['reporter'] = get_reporter(res.get('reporter_id'))  # enrich: id -> email
        hr = tableToMarkdown("Report Summary:", res, headerTransform=split_snake, removeNull=True)
        ec = {'Cofense.Report(val.ID && val.ID == obj.ID)': snake_to_camel_keys([res])}
        return_outputs(readable_output=hr, outputs=ec)

    else:
        return_error('Could not find report with matching ID')


def get_threat_indicators(indicator_type=None, level=None, start_date=None, end_date=None, page=None, per_page=None) -> list:
    params = {}
    params['type'] = indicator_type
    params['level'] = level
    params['start_date'] = start_date
    params['end_date'] = end_date
    params['page'] = page
    params['per_page'] = per_page
    results = TRIAGE_INSTANCE.request("triage_threat_indicators", params=params)

    if not isinstance(results, list):
        results = [results]

    return results


def get_threat_indicators_command() -> None:
    demisto.log('testing')
    # arguments importing
    indicator_type = demisto.getArg('type')
    level = demisto.getArg('level')
    start_date = demisto.getArg('start_date')
    end_date = demisto.getArg('end_date')
    page = demisto.getArg('page')
    per_page = demisto.getArg('per_page')

    results = get_threat_indicators(
        indicator_type, level, start_date, end_date, page, per_page
    )
    demisto.log(str(results))


# parsing outputs
    if results:
        ec = {'Cofense.ThreatIndicators(val.ID && val.ID == obj.ID)': snake_to_camel_keys(results)}
        hr = tableToMarkdown(
            "Threat Indicators:", results, headerTransform=split_snake, removeNull=True
        )

        demisto.results({
            'Type': entryTypes['note'],
            'ContentsFormat': formats['markdown'],
            'Contents': results if results else "no results were found",
            'HumanReadable': hr,
            'EntryContext': ec
        })
    else:
        return_outputs("no results were found.", {})


def get_report_png_by_id_command() -> None:
    report_id = int(demisto.getArg('report_id'))  # type: int
    set_white_bg = demisto.args().get('set_white_bg', 'False') == 'True'  # type: bool

    orig_png = get_report_png_by_id(report_id)

    if set_white_bg:
        inbuf = BytesIO()
        inbuf.write(orig_png)
        inbuf.seek(0)

        image = Image.open(inbuf)
        canvas = Image.new(
            'RGBA', image.size, (255, 255, 255, 255)
        )  # Empty canvas colour (r,g,b,a)
        canvas.paste(
            image, mask=image
        )  # Paste the image onto the canvas, using it's alpha channel as mask

        outbuf = BytesIO()
        canvas.save(outbuf, format="PNG")
        outbuf.seek(0)

        imgdata = outbuf.getvalue()
    else:
        imgdata = orig_png

    cf_file = fileResult(
        "cofense_report_{}.png".format(report_id), imgdata, entryTypes["image"]
    )
    demisto.results(
        {
            "Type": entryTypes["image"],
            "ContentsFormat": formats["text"],
            "Contents": "Cofense: PNG of Report {}".format(report_id),
            "File": cf_file.get("File"),
            "FileID": cf_file.get("FileID"),
        }
    )


def get_report_png_by_id(report_id):
    """Fetch and return the PNG file associated with the specified report_id"""
    return TRIAGE_INSTANCE.request(
        f"reports/{report_id}.png", raw_response=True
    ).content


def parse_report_body(report) -> None:
    if 'report_body' in report and 'HTML' in report['report_body']:
        attachment = fileResult(
            filename=f'{report.get("id")}-report.html',
            data=report.get('report_body').encode(),
        )
        attachment[
            'HumanReadable'
        ] = '### Cofense HTML Report:\nHTML report download request has been completed'
        demisto.results(attachment)
        del report['report_body']


try:
    handle_proxy()

    # COMMANDS
    if demisto.command() == 'test-module':
        test_function()

    if demisto.command() == 'fetch-incidents':
        fetch_reports()

    elif demisto.command() == 'cofense-search-reports':
        search_reports_command()

    elif demisto.command() == 'cofense-get-attachment':
        get_attachment_command()

    elif demisto.command() == 'cofense-get-reporter':
        get_reporter_command()

    elif demisto.command() == 'cofense-get-report-by-id':
        get_report_by_id_command()

    elif demisto.command() == 'cofense-get-report-png-by-id':
        get_report_png_by_id_command()

    elif demisto.command() == 'cofense-get-threat-indicators':
        get_threat_indicators_command()

except Exception as e:
    return_error(str(e))
    raise

"""
ExportDownloadCookieMiddleware echoes an export request's `hlv_export_token`
back in a cookie once the response is a file, which is what lets the browser
close its "Exporting..." dialog (static/index/index.js).
"""

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from horilla.horilla_middlewares import ExportDownloadCookieMiddleware


def _run(response, **query):
    request = RequestFactory().get("/employee/work-info-export/", query)
    return ExportDownloadCookieMiddleware(lambda request: response)(request)


class ExportDownloadCookieMiddlewareTests(SimpleTestCase):
    def test_attachment_with_token_sets_cookie(self):
        response = HttpResponse(b"data")
        response["Content-Disposition"] = 'attachment; filename="employee_export.xlsx"'
        result = _run(response, hlv_export_token="abc123")
        self.assertEqual(result.cookies["hlv_export_done"].value, "abc123")

    def test_inline_pdf_counts_as_a_file(self):
        response = HttpResponse(b"%PDF", content_type="application/pdf")
        result = _run(response, hlv_export_token="abc123")
        self.assertIn("hlv_export_done", result.cookies)

    def test_html_response_gets_no_cookie(self):
        result = _run(HttpResponse("<p>error</p>"), hlv_export_token="abc123")
        self.assertNotIn("hlv_export_done", result.cookies)

    def test_no_token_no_cookie(self):
        response = HttpResponse(b"data")
        response["Content-Disposition"] = 'attachment; filename="x.xlsx"'
        self.assertNotIn("hlv_export_done", _run(response).cookies)

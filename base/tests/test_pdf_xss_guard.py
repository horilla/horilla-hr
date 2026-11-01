"""
generate_pdf must not hand an injected body to wkhtmltopdf.

pdfkit 1.0.0 carries PYSEC-2026-2860 -- `from_string` allows script execution
and local-file exfiltration -- and there is no upstream fix. Every call site
passes `enable-local-file-access` (needed for local CSS and images), which is
the exact configuration the advisory describes.

horilla_automations/signals.py already checked its own rendered body before
calling generate_pdf. Four other callers did not, so the guard lives in
generate_pdf where all five route through.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from base.methods import generate_pdf


class GeneratePdfXssGuardTests(SimpleTestCase):
    def test_script_payload_is_refused(self):
        response = generate_pdf(
            "<html><body><script>fetch('/etc/passwd')</script></body></html>",
            {},
            path=False,
            title="Document",
        )

        self.assertEqual(response.status_code, 400)

    def test_local_file_exfiltration_payload_is_refused(self):
        # The shape the advisory describes: read a local file, post it out.
        payload = (
            "<html><body><script>"
            "var x=new XMLHttpRequest();"
            "x.open('GET','file:///etc/passwd');"
            "x.send();"
            "</script></body></html>"
        )

        response = generate_pdf(payload, {}, path=False, title="Document")

        self.assertEqual(response.status_code, 400)

    def test_onerror_handler_is_refused(self):
        response = generate_pdf(
            "<img src=x onerror=\"fetch('//evil.test')\">",
            {},
            path=False,
            title="Document",
        )

        self.assertEqual(response.status_code, 400)

    def test_ordinary_payslip_markup_still_renders(self):
        # Over-blocking would break payslip and document generation outright,
        # so the negative case matters as much as the positive ones.
        #
        # pdfkit is stubbed: CI has no wkhtmltopdf, and template_pdf turns any
        # pdfkit failure into a 500, so asserting only "not 400" passed even
        # when no PDF was produced. With the stub the response must be a real
        # 200 PDF, which proves the guard let the markup through.
        markup = (
            "<html><body><h1>Payslip</h1><table><tr><td>Basic</td>"
            "<td>50000</td></tr></table></body></html>"
        )
        with patch("base.methods.pdfkit.from_string", return_value=b"%PDF-1.4") as pdf:
            response = generate_pdf(markup, {}, path=False, title="Payslip")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4")
        self.assertIn(markup, pdf.call_args.args[0])

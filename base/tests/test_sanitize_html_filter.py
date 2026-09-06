"""
Rich-text fields were rendered with |safe, so the only guard against stored
XSS was the has_xss regex at write time -- a blocklist, not a parser. The
sanitize_html filter strips to an allow-list instead.
"""

from django.template import Context, Template
from django.test import TestCase

from base.templatetags.basefilters import sanitize_html


class SanitizeHtmlTests(TestCase):
    def test_formatting_is_preserved(self):
        html = "<p>Hello <b>world</b><br><ul><li>one</li></ul></p>"
        out = sanitize_html(html)
        for fragment in ("<p>", "<b>world</b>", "<br>", "<li>one</li>"):
            self.assertIn(fragment, out)

    def test_script_tag_removed(self):
        out = sanitize_html("<p>hi</p><script>alert(1)</script>")
        self.assertNotIn("<script", out)
        self.assertIn("<p>hi</p>", out)

    def test_event_handler_removed(self):
        self.assertNotIn("onerror", sanitize_html("<img src=x onerror=alert(1)>"))

    def test_javascript_url_removed(self):
        out = sanitize_html('<a href="javascript:alert(1)">click</a>')
        self.assertNotIn("javascript:", out)

    def test_iframe_and_style_removed(self):
        out = sanitize_html('<iframe src="//evil"></iframe><style>x{}</style>')
        self.assertNotIn("<iframe", out)
        self.assertNotIn("<style", out)

    def test_safe_link_survives(self):
        out = sanitize_html('<a href="https://example.com" target="_blank">ok</a>')
        self.assertIn('href="https://example.com"', out)

    def test_empty_values(self):
        self.assertEqual(sanitize_html(None), "")
        self.assertEqual(sanitize_html(""), "")

    def test_filter_is_registered_and_marks_safe(self):
        """Rendered through the template engine, output must not be double-escaped."""
        rendered = Template("{% load basefilters %}{{ value|sanitize_html }}").render(
            Context({"value": "<b>bold</b><script>x</script>"})
        )
        self.assertIn("<b>bold</b>", rendered)
        self.assertNotIn("&lt;b&gt;", rendered)
        self.assertNotIn("<script", rendered)

    # --- images and inline styling -------------------------------------
    #
    # The first version of this filter allowed neither, which silently
    # emptied every screenshot out of existing ticket descriptions and
    # dropped colour from existing rich text. Nothing was destroyed -- the
    # filter only affects rendering -- but the content read wrong until it
    # was allowed back.

    def test_hosted_image_survives(self):
        """People paste screenshots into ticket descriptions."""
        out = sanitize_html('<p>See <img src="https://x.test/a.png" alt="err"></p>')
        self.assertIn("<img", out)
        self.assertIn('src="https://x.test/a.png"', out)
        self.assertIn('alt="err"', out)

    def test_image_dimensions_survive(self):
        out = sanitize_html('<img src="https://x.test/a.png" width="600" height="80">')
        self.assertIn('width="600"', out)
        self.assertIn('height="80"', out)

    def test_image_javascript_src_removed(self):
        self.assertNotIn(
            "javascript:", sanitize_html('<img src="javascript:alert(1)">')
        )

    def test_image_data_uri_removed(self):
        """A data: URI can carry text/html, so it is a script delivery vector.

        The cost is that a screenshot inlined as base64 by the editor does not
        survive; a hosted one does. That trade is deliberate.
        """
        out = sanitize_html(
            '<img src="data:text/html;base64,PHNjcmlwdD54PC9zY3JpcHQ+">'
        )
        self.assertNotIn("data:", out)

    def test_image_event_handler_removed(self):
        out = sanitize_html('<img src="https://x.test/a.png" onerror="alert(1)">')
        self.assertIn("<img", out)
        self.assertNotIn("onerror", out)

    def test_inline_colour_survives(self):
        out = sanitize_html('<p style="color:red">Urgent</p>')
        self.assertIn("color:red", out.replace(" ", ""))

    def test_inline_highlight_survives(self):
        out = sanitize_html('<span style="background-color:yellow">note</span>')
        self.assertIn("background-color:yellow", out.replace(" ", ""))

    def test_disallowed_css_property_dropped(self):
        out = sanitize_html('<p style="position:fixed;color:red">x</p>')
        self.assertNotIn("position", out)
        self.assertIn("color:red", out.replace(" ", ""))

    def test_css_function_values_are_dropped(self):
        """bleach checks the property NAME but not its VALUE.

        Verified against bleach 6.4.0: `color: expression(alert(1))` passes its
        own filter untouched, because `color` is allowed. Restricting the
        property list does not help -- the payload rides on whichever property
        is permitted -- so _StrictCSSSanitizer drops any value containing a
        function call. This is the test that catches its removal.
        """
        for css in (
            "color:expression(alert(1))",
            "width:expression(alert(1))",
            "background-color:url(javascript:alert(1))",
        ):
            with self.subTest(css=css):
                out = sanitize_html(f'<p style="{css}">x</p>')
                self.assertNotIn("expression(", out)
                self.assertNotIn("javascript:", out)
                self.assertNotIn("url(", out)

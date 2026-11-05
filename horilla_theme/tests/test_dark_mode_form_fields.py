"""dark.css: form fields look alike, and their browser-drawn parts can be seen."""

import re
from pathlib import Path

from django.test import SimpleTestCase

DARK_CSS = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "horilla_theme"
    / "assets"
    / "css"
    / "dark.css"
)


def rule_with(selector):
    css = re.sub(r"/\*.*?\*/", "", DARK_CSS.read_text(), flags=re.DOTALL)
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in selectors.split(",")]:
            yield body


class TestDarkModeFormFields(SimpleTestCase):
    def test_text_areas_share_the_background_of_inputs(self):
        backgrounds = lambda selector: {  # noqa: E731
            body.strip()
            for body in rule_with(selector)
            if "background-color" in body and "!important" in body
        }
        self.assertTrue(backgrounds("body.dark input"))
        self.assertEqual(
            backgrounds("body.dark input"), backgrounds("body.dark textarea")
        )

    def test_date_and_time_inputs_tell_the_browser_the_page_is_dark(self):
        for kind in ("date", "time", "datetime-local", "month", "week"):
            with self.subTest(kind=kind):
                bodies = list(rule_with(f'body.dark input[type="{kind}"]'))
                self.assertTrue(any("color-scheme: dark" in b for b in bodies))

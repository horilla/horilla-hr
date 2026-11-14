"""header_scripts.html keeps the in-browser Tailwind compiler from losing classes."""

import re
from pathlib import Path

from django.test import SimpleTestCase

APP = Path(__file__).resolve().parents[1]
HEADER_SCRIPTS = (
    APP / "templates" / "horilla_theme" / "components" / "header_scripts.html"
)
COMPILERS = [
    APP / "static" / "horilla_theme" / "assets" / "js" / name
    for name in ("tailwind.js", "tailwindcdn.js")
]


class TestTailwindLostClasses(SimpleTestCase):
    def test_both_compilers_pass_classes_through_the_global_the_fix_wraps(self):
        template = HEADER_SCRIPTS.read_text()
        key = re.search(r'var key = "([^"]+)";', template).group(1)
        for compiler in COMPILERS:
            with self.subTest(compiler=compiler.name):
                source = compiler.read_text()
                self.assertRegex(source, rf'_v\s*=\s*"{re.escape(key)}"')
                self.assertRegex(source, r"self\[_v\]\s*=")

    def test_the_global_keeps_every_class_it_is_given(self):
        template = HEADER_SCRIPTS.read_text()
        self.assertIn("Object.defineProperty(self, key, {", template)
        self.assertIn("set: add,", template)
        self.assertIn('return Array.from(seen).join(" ");', template)

    def test_the_fix_runs_after_the_compiler_loads(self):
        template = HEADER_SCRIPTS.read_text()
        self.assertLess(
            template.index("horilla_theme/assets/js/tailwind.js"),
            template.index("Object.defineProperty(self, key, {"),
        )

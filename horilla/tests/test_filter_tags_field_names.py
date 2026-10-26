"""
Filter field names come from the query string, and the filter tags script
writes them into a JavaScript template literal. They must reach it as escaped
data: `${...}`, a backtick, a quote or a backslash in a name must not become
part of the script.
"""

from django.template.loader import render_to_string
from django.test import TestCase

HOSTILE_NAMES = [
    "${alert(document.domain)}",
    "`+alert(1)+`",
    'a"><img src=x onerror=alert(1)>',
    "a\\",
    "a\nb",
]


def render(names):
    """The script block of the filter tags, which is where the names are used."""
    out = render_to_string(
        "filter_tags.html", {"filter_dict": {name: ["x"] for name in names}}
    )
    return out[out.index("<script>") : out.index("</script>")]


class FilterTagFieldNameTests(TestCase):
    def test_a_normal_field_name_is_unchanged(self):
        out = render(["employee_id__icontains"])
        self.assertIn('data-x-field="employee_id__icontains"', out)
        self.assertIn('"employee_id__icontains")}', out)

    def test_field_names_cannot_add_script_syntax(self):
        baseline = render(["employee_id__icontains"])
        for name in HOSTILE_NAMES:
            with self.subTest(name=name):
                out = render([name])
                # The same number of template-literal delimiters and
                # interpolations as for a harmless name: nothing new opens
                # or closes the literal.
                self.assertEqual(out.count("`"), baseline.count("`"))
                self.assertEqual(out.count("${"), baseline.count("${"))
                # No raw newline, escaped quote or markup comes from the name.
                self.assertEqual(out.count("\n"), baseline.count("\n"))
                self.assertEqual(out.count('\\"'), baseline.count('\\"'))
                self.assertNotIn("<img", out)

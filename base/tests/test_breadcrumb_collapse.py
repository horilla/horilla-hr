from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from base.templatetags.basefilters import collapse_breadcrumbs


def _trail(count):
    return [
        {"name": f"Step {n}", "url": f"/step-{n}/", "clickable": True, "found": True}
        for n in range(1, count + 1)
    ]


class CollapseBreadcrumbsTests(SimpleTestCase):
    def test_a_short_trail_is_left_whole(self):
        groups = collapse_breadcrumbs(_trail(4))
        self.assertFalse(groups["collapsed"])
        self.assertEqual(len(groups["all"]), 4)

    def test_a_long_trail_keeps_the_first_and_last_two_and_folds_the_rest(self):
        groups = collapse_breadcrumbs(_trail(6))
        self.assertTrue(groups["collapsed"])
        self.assertEqual(groups["first"]["name"], "Step 1")
        self.assertEqual(
            [c["name"] for c in groups["hidden"]], ["Step 2", "Step 3", "Step 4"]
        )
        self.assertEqual([c["name"] for c in groups["tail"]], ["Step 5", "Step 6"])


class BreadcrumbTemplateTests(TestCase):
    # TestCase, not Simple: the template loader reads templates from the database too.
    def _render(self, count):
        request = RequestFactory().get("/step-6/")
        return render_to_string(
            "base/navbar_components/breadcrumbs_view.html",
            {"breadcrumbs": _trail(count), "request": request},
        )

    def test_a_long_trail_shows_a_plus_chip_with_the_hidden_steps_in_it(self):
        html = self._render(6)
        self.assertIn(">+3<", html)
        self.assertIn('href="/step-2/"', html)  # in the list
        self.assertIn('href="/step-6/"', html)  # the current page, still on the trail

    def test_a_short_trail_has_no_chip(self):
        self.assertNotIn('crumb-more">', self._render(3))

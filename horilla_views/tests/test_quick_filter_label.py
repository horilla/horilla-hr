"""The quick filter dropdown (quick dates + saved filters) is labelled "Quick
filter", so it isn't confused with the nav's "Filter" panel button."""

from django.template.loader import get_template
from django.test import TestCase


class QuickFilterLabelTests(TestCase):
    def render(self, template, **context):
        # No request: these partials don't need the context processors.
        context = {"view_id": "v1", "selected_instances_key_id": "sel", **context}
        return get_template(template).render(context)

    def test_the_list_dropdown_is_called_quick_filter(self):
        html = self.render(
            "generic/quick_actions.html",
            show_quick_date_filters=True,
            quick_date_filters=[("Today", 'onclick=""')],
        )
        self.assertIn("Quick filter", html)
        self.assertNotRegex(html, r">\s*Filter\s*<ion-icon")

    def test_the_pipeline_dropdowns_are_called_quick_filter(self):
        # Shaped like a SavedFilter (the fields _saved_filter_chip.html reads).
        stored = [{"id": 1, "title": "Mine", "urlencode": "a=1", "color": ""}]
        for template in (
            "cbv/pipeline/quick_actions.html",
            "cbv/pipeline/onboarding/quick_actions.html",
            "cbv/exit_process/quick_actions.html",
        ):
            with self.subTest(template=template):
                html = self.render(template, stored_filters=stored)
                self.assertIn("Quick filter (1)", html)
                self.assertIn("Mine", html)

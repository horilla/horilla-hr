"""The quick filter dropdowns render a user's saved filters as chips."""

from django.template.loader import get_template
from django.test import TestCase


class QuickFilterSavedChipTests(TestCase):
    def render(self, template, **context):
        # No request: these partials don't need the context processors.
        context = {"view_id": "v1", "selected_instances_key_id": "sel", **context}
        return get_template(template).render(context)

    def test_the_pipeline_dropdowns_render_the_saved_filter_chip(self):
        # Shaped like a SavedFilter (the fields _saved_filter_chip.html reads).
        stored = [{"id": 1, "title": "Mine", "urlencode": "a=1", "color": ""}]
        for template in (
            "cbv/pipeline/quick_actions.html",
            "cbv/pipeline/onboarding/quick_actions.html",
            "cbv/exit_process/quick_actions.html",
        ):
            with self.subTest(template=template):
                html = self.render(template, stored_filters=stored)
                self.assertIn("Mine", html)

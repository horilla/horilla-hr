"""The documentation environment leaves out the modules that are not released."""

from django.test import SimpleTestCase

from horilla import docs_settings
from horilla.settings import base


class DocsSettingsTests(SimpleTestCase):
    def test_unreleased_modules_are_not_installed_or_in_the_sidebar(self):
        for app in docs_settings.UNRELEASED_APPS:
            self.assertNotIn(app, docs_settings.INSTALLED_APPS)
            self.assertNotIn(app, docs_settings.SIDEBARS)

    def test_everything_else_is_kept_in_order(self):
        kept = [
            a for a in base.INSTALLED_APPS if a not in docs_settings.UNRELEASED_APPS
        ]
        self.assertEqual(docs_settings.INSTALLED_APPS, kept)
        self.assertEqual(
            docs_settings.SIDEBARS,
            [a for a in base.SIDEBARS if a not in docs_settings.UNRELEASED_APPS],
        )

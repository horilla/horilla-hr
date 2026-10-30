"""Theme model smoke tests."""

from django.test import TestCase

from horilla_theme.models import THEMES_DATA, HorillaColorTheme


class ThemeCreateTests(TestCase):
    def test_create_from_theme_data(self):
        data = dict(THEMES_DATA[1])
        data["name"] = "Unit Smoke Ocean Theme"
        data["is_default"] = False
        theme = HorillaColorTheme.objects.create(**data)
        self.assertIsNotNone(theme.pk)
        self.assertEqual(theme.primary_600, "#3b82f6")

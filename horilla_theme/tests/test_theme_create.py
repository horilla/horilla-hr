"""Theme model smoke tests."""

from django.test import TestCase

from horilla_theme.models import THEMES_DATA, HorillaColorTheme


class ThemeCreateTests(TestCase):
    def test_every_seeded_theme_can_be_created(self):
        # THEMES_DATA is what the post_migrate signal and create_default_themes
        # insert, so every key in it must be a real model field. No colour
        # values are asserted: recolouring a theme is not a defect.
        for index, theme_data in enumerate(THEMES_DATA):
            with self.subTest(theme=theme_data.get("name", index)):
                data = dict(theme_data)
                data["name"] = f"Unit Smoke Theme {index}"
                data["is_default"] = False
                theme = HorillaColorTheme.objects.create(**data)
                self.assertIsNotNone(theme.pk)

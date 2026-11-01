"""Breadcrumb menu-section resolution."""

from django.test import SimpleTestCase

from horilla_crumbs.context_processors import _resolve_menu_section


class ResolveMenuSectionTests(SimpleTestCase):
    def test_longest_submenu_match(self):
        menus = [
            {
                "menu": "People",
                "submenu": [
                    {"redirect": "/employee/"},
                    {"redirect": "/employee/list/"},
                ],
            }
        ]
        result = _resolve_menu_section("/employee/list/detail/", menus)
        self.assertEqual(result, ("People", "/employee/list/"))

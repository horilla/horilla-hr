"""Horilla views CBV helper smoke tests."""

from django.test import SimpleTestCase

from horilla_views.cbv_methods import merge_dicts


class CbvHelperTests(SimpleTestCase):
    def test_merge_dicts_extends_lists(self):
        merged = merge_dicts(
            {"k": {"M": [1]}},
            {"k": {"M": [2], "N": [3]}},
        )
        self.assertEqual(merged["k"]["M"], [1, 2])
        self.assertEqual(merged["k"]["N"], [3])

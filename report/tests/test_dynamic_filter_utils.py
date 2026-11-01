"""Report dynamic filter util smoke tests."""

import datetime
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from report.dynamic_filter_utils import (
    RELATIVE_DATE_OPERATORS,
    parse_multi_value,
    resolve_relative_date_range,
)

# A Wednesday, so "this week" starts on the 9th and ends on the 15th.
FIXED_TODAY = date(2026, 3, 11)


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return FIXED_TODAY


class ResolveRelativeDateRangeTests(SimpleTestCase):
    def setUp(self):
        # The helper reads ``datetime.date.today()``. Pin it so the result does
        # not depend on the clock (or on a run that straddles midnight).
        clock = patch(
            "report.dynamic_filter_utils.datetime",
            SimpleNamespace(date=_FrozenDate, timedelta=datetime.timedelta),
        )
        clock.start()
        self.addCleanup(clock.stop)

    def test_relative_operators_resolve_against_the_fixed_day(self):
        expected = {
            "today": (date(2026, 3, 11), date(2026, 3, 11)),
            "yesterday": (date(2026, 3, 10), date(2026, 3, 10)),
            "this_week": (date(2026, 3, 9), date(2026, 3, 15)),
            "last_week": (date(2026, 3, 2), date(2026, 3, 8)),
            "this_month": (date(2026, 3, 1), date(2026, 3, 31)),
            "last_month": (date(2026, 2, 1), date(2026, 2, 28)),
            "this_year": (date(2026, 1, 1), date(2026, 12, 31)),
            "last_year": (date(2025, 1, 1), date(2025, 12, 31)),
        }
        self.assertEqual(set(expected), set(RELATIVE_DATE_OPERATORS))
        for operator, window in expected.items():
            with self.subTest(operator=operator):
                self.assertEqual(resolve_relative_date_range(operator), window)

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_relative_date_range("not_an_op"))


class ParseMultiValueTests(SimpleTestCase):
    def test_json_array(self):
        self.assertEqual(parse_multi_value('["a","b"]'), ["a", "b"])

    def test_plain_string(self):
        self.assertEqual(parse_multi_value("Sales"), ["Sales"])

"""Quick Date menu ranges (horilla_views.cbv_methods.get_quick_date_filters)."""

import re
from datetime import date
from unittest import mock

from django.test import SimpleTestCase, override_settings

from horilla_views.cbv_methods import (
    first_day_of_week,
    get_quick_date_filters,
    week_start,
)
from horilla_views.generic.cbv.views import QUICK_DATE_RANGES

FIELDS = ("attendance_date", "attendance_date__gte", "attendance_date__lte")
WEDNESDAY = date(2026, 10, 21)


def ranges_on(today):
    """{label: (from, to)} as the menu would set them on `today`."""
    with mock.patch("horilla_views.cbv_methods.timezone.localdate", return_value=today):
        filters = get_quick_date_filters(QUICK_DATE_RANGES, FIELDS)
    out = {}
    for label, attrs in filters:
        values = dict(re.findall(r"\[name=(\w+)\]'\)\.val\('([^']*)'\)", attrs))
        out[str(label)] = (
            values.get("attendance_date__gte") or values.get("attendance_date"),
            values.get("attendance_date__lte") or values.get("attendance_date"),
        )
    return out


# Monday unless a test says otherwise, whatever a local .env sets.
@override_settings(HORILLA_FIRST_DAY_OF_WEEK=1)
class QuickDateFilterTests(SimpleTestCase):
    def test_weeks_start_on_monday_by_default(self):
        self.assertEqual(week_start(WEDNESDAY), date(2026, 10, 19))
        self.assertEqual(week_start(date(2026, 10, 19)), date(2026, 10, 19))  # Monday
        self.assertEqual(week_start(date(2026, 10, 25)), date(2026, 10, 19))  # Sunday

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK=0)
    def test_a_site_can_start_weeks_on_sunday(self):
        self.assertEqual(week_start(WEDNESDAY), date(2026, 10, 18))
        self.assertEqual(week_start(date(2026, 10, 18)), date(2026, 10, 18))  # Sunday
        self.assertEqual(week_start(date(2026, 10, 24)), date(2026, 10, 18))  # Saturday
        menu = ranges_on(WEDNESDAY)
        self.assertEqual(menu["This Week"], ("2026-10-18", "2026-10-24"))
        self.assertEqual(menu["Last Week"], ("2026-10-11", "2026-10-17"))

    def test_first_day_of_week_setting(self):
        for value, expected in [
            (0, 0),
            ("0", 0),
            ("6", 6),
            (" 2 ", 2),
            ("", 1),
            ("abc", 1),
            ("7", 1),
            ("-1", 1),
            (None, 1),
        ]:
            with self.subTest(value=value), override_settings(
                HORILLA_FIRST_DAY_OF_WEEK=value
            ):
                self.assertEqual(first_day_of_week(), expected)

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="abc")
    def test_an_invalid_setting_means_monday(self):
        self.assertEqual(week_start(WEDNESDAY), date(2026, 10, 19))

    def test_this_week_and_last_week_are_calendar_weeks(self):
        menu = ranges_on(WEDNESDAY)
        self.assertEqual(menu["This Week"], ("2026-10-19", "2026-10-25"))
        self.assertEqual(menu["Last Week"], ("2026-10-12", "2026-10-18"))

    def test_on_a_monday_and_on_a_sunday(self):
        monday = ranges_on(date(2026, 10, 19))
        self.assertEqual(monday["This Week"], ("2026-10-19", "2026-10-25"))
        self.assertEqual(monday["Last Week"], ("2026-10-12", "2026-10-18"))
        sunday = ranges_on(date(2026, 10, 25))
        self.assertEqual(sunday["This Week"], ("2026-10-19", "2026-10-25"))
        self.assertEqual(sunday["Last Week"], ("2026-10-12", "2026-10-18"))

    def test_across_a_year_boundary(self):
        new_year = ranges_on(date(2027, 1, 1))  # a Friday
        self.assertEqual(new_year["This Week"], ("2026-12-28", "2027-01-03"))
        self.assertEqual(new_year["Last Week"], ("2026-12-21", "2026-12-27"))
        self.assertEqual(new_year["Last 7 Days"], ("2026-12-26", "2027-01-01"))
        self.assertEqual(new_year["Next 7 Days"], ("2027-01-01", "2027-01-07"))

    def test_seven_day_ranges_include_today(self):
        menu = ranges_on(WEDNESDAY)
        self.assertEqual(menu["Last 7 Days"], ("2026-10-15", "2026-10-21"))
        self.assertEqual(menu["Next 7 Days"], ("2026-10-21", "2026-10-27"))

    def test_single_days_are_unchanged(self):
        menu = ranges_on(WEDNESDAY)
        self.assertEqual(menu["Yesterday"], ("2026-10-20", "2026-10-20"))
        self.assertEqual(menu["Today"], ("2026-10-21", "2026-10-21"))
        self.assertEqual(menu["Tomorrow"], ("2026-10-22", "2026-10-22"))

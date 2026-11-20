"""
Sorting a list by a day-of-week column follows the week (Mon, Tue, ... Sun,
starting on HORILLA_FIRST_DAY_OF_WEEK), not the alphabet (Fri, Mon, Sat, ...).
"""

from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from attendance.models import Attendance
from base.cbv.company_leaves import CompanyleaveListView
from base.models import CompanyLeaves, EmployeeShiftDay
from horilla.horilla_middlewares import _thread_locals
from horilla_views.cbv_methods import sortby, weekday_sort_key
from leave.models import LeaveType

NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def week_order(model, sort_key, values):
    position = weekday_sort_key(model, sort_key)
    return sorted(values, key=position)


class WeekdaySortKeyTests(SimpleTestCase):
    def test_day_names_sort_monday_first_by_default(self):
        self.assertEqual(
            week_order(EmployeeShiftDay, "day", sorted(NAMES)),
            NAMES,
        )

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="0")
    def test_week_starting_sunday(self):
        self.assertEqual(
            week_order(EmployeeShiftDay, "day", sorted(NAMES)),
            NAMES[-1:] + NAMES[:-1],
        )

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="6")
    def test_week_starting_saturday(self):
        self.assertEqual(
            week_order(EmployeeShiftDay, "day", sorted(NAMES)),
            NAMES[-2:] + NAMES[:-2],
        )

    def test_follows_a_relation_to_the_day(self):
        # The Attendances list's "Day" column.
        self.assertEqual(
            week_order(
                Attendance, "attendance_day__day", ["sunday", "friday", "monday"]
            ),
            ["monday", "friday", "sunday"],
        )

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="0")
    def test_numbered_week_days(self):
        # WEEK_DAYS stores "0" (Monday) to "6" (Sunday).
        self.assertEqual(
            week_order(CompanyLeaves, "based_on_week_day", ["0", "6", "4"]),
            ["6", "0", "4"],
        )
        self.assertEqual(
            week_order(LeaveType, "reset_weekend", ["5", "0", "6"]),
            ["6", "0", "5"],
        )

    def test_unknown_value_sorts_after_the_week(self):
        self.assertEqual(
            week_order(EmployeeShiftDay, "day", ["holiday", "sunday", "monday"]),
            ["monday", "sunday", "holiday"],
        )

    def test_other_columns_are_left_alone(self):
        for model, sort_key in [
            (CompanyLeaves, "based_on_week"),  # "0" to "4": weeks, not days
            (Attendance, "attendance_date"),
            (Attendance, "attendance_day"),  # the relation itself
            (Attendance, "employee_id__get_full_name"),  # a method
            (Attendance, "no_such_field"),
        ]:
            with self.subTest(sort_key=sort_key):
                self.assertIsNone(weekday_sort_key(model, sort_key))

    def test_weekly_off_days_sort_by_the_stored_day(self):
        # It used to sort by the rendered column, so alphabetically.
        self.assertIn(
            ("Based On Week Day", "based_on_week_day"),
            CompanyleaveListView.sortby_mapping,
        )


class WeekdaySortbyTests(TestCase):
    def setUp(self):
        for name in NAMES:
            EmployeeShiftDay.objects.get_or_create(day=name)
        request = RequestFactory().get("/")
        request.session = SessionStore()
        request.session.create()
        _thread_locals.request = request
        self.addCleanup(setattr, _thread_locals, "request", None)

    def sort(self):
        days = sortby(
            {"sortby": "day"},
            EmployeeShiftDay.objects.filter(day__in=NAMES),
            "sortby",
        )
        return tuple(day.day for day in days)

    def test_list_sorts_through_the_week_both_ways(self):
        # Two clicks on the column: one direction, then the other.
        self.assertEqual(
            {self.sort(), self.sort()},
            {tuple(NAMES), tuple(NAMES[::-1])},
        )

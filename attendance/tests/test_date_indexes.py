"""
Indexes on the date columns these tables are actually filtered by.

Before this, Meta.indexes was empty on Attendance, LeaveRequest and Payslip
while the codebase carried ~100 range filters on attendance_date and ~240 on
start_date/end_date. Repo-wide, AddIndex had appeared in two migration
operations in one app, ever.

The composite indexes Django creates from unique_together/UniqueConstraint do
not help: they lead on employee_id, so a date-range scan that does not pin an
employee cannot use them -- which is what every dashboard and report does.
"""

from datetime import date

from django.test import TestCase


class DateIndexTests(TestCase):
    def _index_fields(self, model):
        return {tuple(index.fields) for index in model._meta.indexes}

    def test_attendance_date_is_indexed(self):
        from attendance.models import Attendance

        fields = self._index_fields(Attendance)
        self.assertIn(("attendance_date",), fields)
        self.assertIn(("attendance_date", "attendance_validated"), fields)

    def test_leave_request_dates_are_indexed(self):
        from leave.models import LeaveRequest

        fields = self._index_fields(LeaveRequest)
        self.assertIn(("start_date", "end_date"), fields)
        self.assertIn(("status", "start_date"), fields)

    def test_payslip_dates_are_indexed(self):
        from payroll.models.models import Payslip

        fields = self._index_fields(Payslip)
        # Descending, to match Meta.ordering = ["-end_date"].
        self.assertIn(("-end_date",), fields)
        self.assertIn(("status", "end_date"), fields)

    def test_indexes_exist_in_the_database(self):
        """Declaring them is not enough -- the migration must have run."""
        from django.db import connection

        from attendance.models import Attendance

        with connection.cursor() as cursor:
            existing = connection.introspection.get_constraints(
                cursor, Attendance._meta.db_table
            )
        names = set(existing)
        self.assertIn("attendance_date_idx", names)
        self.assertIn("attendance_date_validated_idx", names)


class MonthPredicateTests(TestCase):
    """
    __month=/__year= wrap the column in a database function, so a B-tree index
    on that column cannot be used no matter what is declared above. These
    queries were rewritten to range predicates; this guards the rewrite.
    """

    def test_month_date_range_matches_calendar_months(self):
        from attendance.methods.utils import month_date_range

        self.assertEqual(
            month_date_range(2026, 1), (date(2026, 1, 1), date(2026, 1, 31))
        )
        # Leap and non-leap February.
        self.assertEqual(
            month_date_range(2024, 2), (date(2024, 2, 1), date(2024, 2, 29))
        )
        self.assertEqual(
            month_date_range(2026, 2), (date(2026, 2, 1), date(2026, 2, 28))
        )
        self.assertEqual(
            month_date_range(2026, 12), (date(2026, 12, 1), date(2026, 12, 31))
        )

    def test_month_date_range_accepts_strings(self):
        """AttendanceOverTime.year is a CharField."""
        from attendance.methods.utils import month_date_range

        self.assertEqual(
            month_date_range("2026", "3"), (date(2026, 3, 1), date(2026, 3, 31))
        )

    def test_attendance_queries_avoid_function_wrapped_dates(self):
        import inspect

        from attendance import models

        source = inspect.getsource(models)
        self.assertNotIn("attendance_date__month=", source)
        self.assertNotIn("attendance_date__year=", source)

    def test_overtime_hour_methods_aggregate_in_the_database(self):
        """Both methods used to pull every row into Python to sum it."""
        import inspect

        from attendance.models import AttendanceOverTime

        for method in (
            AttendanceOverTime.not_validated_hrs,
            AttendanceOverTime.not_approved_ot_hrs,
        ):
            with self.subTest(method=method.__name__):
                source = inspect.getsource(method)
                self.assertIn("aggregate(", source)
                self.assertNotIn("sum(", source)

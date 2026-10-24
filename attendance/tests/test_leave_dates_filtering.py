"""Tests for work-record leave_dates holiday filtering."""

from django.test import TestCase

from attendance.methods.utils import monthly_leave_days
from attendance.tests.fixtures import HolidayFixtureMixin
from base.models import Holidays


class TestLeaveDatesFiltering(HolidayFixtureMixin, TestCase):
    """
    Mirrors the logic in work_records_change_month that builds leave_dates.
    Specific holiday dates must be filtered out so they don't mark the
    entire work-record column as a holiday for every employee.
    """

    def _build_leave_dates(self, target_date):
        """Replicate the view's leave_dates construction for a given month."""
        month, year = target_date.month, target_date.year
        specific_dates = set(
            Holidays.objects.filter(
                is_specific=True,
                start_date__month=month,
                start_date__year=year,
            ).values_list("start_date", flat=True)
        )
        return [d for d in monthly_leave_days(month, year) if d not in specific_dates]

    def test_global_holiday_included_in_leave_dates(self):
        """Global holiday must appear in leave_dates for all employees."""
        leave_dates = self._build_leave_dates(self.global_date)
        self.assertIn(self.global_date, leave_dates)

    def test_specific_holiday_excluded_from_leave_dates(self):
        """
        Specific holiday must NOT appear in leave_dates — it applies
        only to individual employees, not all columns.
        """
        leave_dates = self._build_leave_dates(self.specific_date)
        self.assertNotIn(self.specific_date, leave_dates)

    def test_normal_date_not_in_leave_dates(self):
        """A regular working day must not appear in leave_dates."""
        leave_dates = self._build_leave_dates(self.normal_date)
        self.assertNotIn(self.normal_date, leave_dates)


class TestWorkRecordScheduledDayFallback(HolidayFixtureMixin, TestCase):
    """
    Verify that work_records_change_month synthesizes 'DFT' (Absent) records
    only on past/current scheduled working days outside holidays, leaving
    weekly off-days and holidays blank.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from datetime import time

        from base.models import EmployeeShiftSchedule
        from horilla.testkit.factories import make_employee, make_user

        # Schedule only Monday for cls.shift (leaving other weekdays as shift off-days)
        EmployeeShiftSchedule.objects.get_or_create(
            shift_id=cls.shift,
            day=cls.shift_day,
            defaults={
                "start_time": time(9, 0),
                "end_time": time(17, 0),
                "minimum_working_hour": "08:00",
            },
        )
        cls.admin_user = make_user("wr_admin", is_superuser=True)
        make_employee(
            company=cls.company,
            email="wr_admin@holiday.test",
            user=cls.admin_user,
            shift=cls.shift,
        )

    def test_unrecorded_scheduled_day_gets_dft_while_off_day_stays_none(self):
        from django.urls import reverse

        self.client.force_login(self.admin_user)
        month_str = f"{self.normal_date.year}-{self.normal_date.month:02d}"
        response = self.client.get(
            reverse("work-records-change-month"),
            {"month": month_str},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        month_dates = response.context["current_month_dates_list"]
        emp_rows = dict(response.context["data"].object_list)
        emp_a_records = dict(zip(month_dates, emp_rows[self.emp_a]))

        # Find a Monday (scheduled) and a Tuesday (off-day) in that past month
        monday = next(
            d for d in month_dates if d.weekday() == 0 and d != self.normal_date
        )
        tuesday = next(
            d for d in month_dates if d.weekday() == 1 and d != self.normal_date
        )

        self.assertIsNotNone(emp_a_records[monday])
        self.assertEqual(emp_a_records[monday].work_record_type, "DFT")
        self.assertIsNone(emp_a_records[tuesday])

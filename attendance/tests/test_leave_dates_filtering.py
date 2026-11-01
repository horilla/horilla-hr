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

    def test_normal_date_not_in_leave_dates(self):
        """A regular working day must not appear in leave_dates."""
        leave_dates = self._build_leave_dates(self.normal_date)
        self.assertNotIn(self.normal_date, leave_dates)

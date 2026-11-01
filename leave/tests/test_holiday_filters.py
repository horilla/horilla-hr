"""Tests for employee-specific holiday filtering in leave."""

from datetime import timedelta

from django.test import TestCase

from base.models import Holidays
from leave.methods import holiday_dates_list
from leave.tests.fixtures import LeaveHolidayFixtureMixin


class TestHolidayDatesList(LeaveHolidayFixtureMixin, TestCase):
    """
    holiday_dates_list() must correctly expand multi-day holiday ranges
    and return the right dates when fed employee-filtered querysets.
    """

    def test_multi_day_range_expands_correctly(self):
        """A 3-day holiday expands to all 3 dates."""
        start = self.past_global - timedelta(days=5)
        end = start + timedelta(days=2)
        h = Holidays.objects.create(
            name="Multi Day",
            start_date=start,
            end_date=end,
            is_specific=False,
            company_id=self.company,
        )
        dates = holiday_dates_list(Holidays.objects.filter(pk=h.pk))
        self.assertEqual(len(dates), 3)
        self.assertIn(start, dates)
        self.assertIn(start + timedelta(days=1), dates)
        self.assertIn(end, dates)


class TestTodayHolidaysMethod(LeaveHolidayFixtureMixin, TestCase):
    """
    Holidays.today_holidays() updated with employee=None parameter.
    Without employee: returns all holidays active today.
    With employee: applies Q(is_specific=False) | Q(employees=employee).
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create a holiday active TODAY to test today_holidays
        cls.today_global = Holidays.objects.create(
            name="Today Global",
            start_date=cls.today,
            end_date=cls.today,
            is_specific=False,
            company_id=cls.company,
        )
        cls.today_specific = Holidays.objects.create(
            name="Today Specific",
            start_date=cls.today,
            # differs from the global holiday's range (unique per company)
            end_date=cls.today + timedelta(days=1),
            is_specific=True,
            assigning_type="employee",
            company_id=cls.company,
        )
        cls.today_specific.employees.add(cls.emp_a)

    def test_no_employee_returns_both_holiday_types(self):
        """today_holidays() without employee returns global and specific holidays."""
        qs = Holidays.today_holidays(today=self.today)
        pks = set(qs.values_list("pk", flat=True))
        self.assertIn(self.today_global.pk, pks)
        self.assertIn(self.today_specific.pk, pks)

    def test_with_emp_a_returns_own_specific_holiday(self):
        """today_holidays(employee=emp_a) includes emp_a's specific holiday."""
        qs = Holidays.today_holidays(today=self.today, employee=self.emp_a)
        pks = set(qs.values_list("pk", flat=True))
        self.assertIn(self.today_global.pk, pks)
        self.assertIn(self.today_specific.pk, pks)

    def test_with_emp_b_excludes_emp_a_specific_holiday(self):
        """today_holidays(employee=emp_b) hides emp_a's specific holiday."""
        qs = Holidays.today_holidays(today=self.today, employee=self.emp_b)
        pks = set(qs.values_list("pk", flat=True))
        self.assertIn(self.today_global.pk, pks)
        self.assertNotIn(self.today_specific.pk, pks)

    def test_past_date_returns_nothing_for_today_holidays(self):
        """today_holidays() for a date with no active holidays returns empty qs."""
        far_past = self.today - timedelta(days=200)
        qs = Holidays.today_holidays(today=far_past)
        self.assertFalse(qs.exists())

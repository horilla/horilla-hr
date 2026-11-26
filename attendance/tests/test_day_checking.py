"""Tests for attendance_day_checking() holiday handling."""

from django.test import TestCase

from attendance.methods.utils import attendance_day_checking
from attendance.tests.fixtures import HolidayFixtureMixin


class TestAttendanceDayChecking(HolidayFixtureMixin, TestCase):
    """
    attendance_day_checking() must return '00:00' only for holidays
    that apply to the given employee.
    """

    def test_global_holiday_no_employee_resets_minimum_hour(self):
        """No employee context: global holiday zeroes minimum_hour."""
        result = attendance_day_checking(str(self.global_date), "08:00")
        self.assertEqual(result, "08:00")

    def test_global_holiday_with_emp_a_resets_minimum_hour(self):
        """emp_a: global holiday zeroes minimum_hour."""
        result = attendance_day_checking(
            str(self.global_date), "08:00", employee=self.emp_a
        )
        self.assertEqual(result, "08:00")

    def test_global_holiday_with_emp_b_resets_minimum_hour(self):
        """emp_b: global holiday also zeroes minimum_hour (applies to all)."""
        result = attendance_day_checking(
            str(self.global_date), "08:00", employee=self.emp_b
        )
        self.assertEqual(result, "08:00")

    def test_specific_holiday_no_employee_does_not_reset(self):
        """No employee context: specific holiday is excluded, hour unchanged."""
        result = attendance_day_checking(str(self.specific_date), "08:00")
        self.assertEqual(result, "08:00")

    def test_specific_holiday_with_assigned_emp_a_resets(self):
        """emp_a is assigned to the specific holiday — hour must become 00:00."""
        result = attendance_day_checking(
            str(self.specific_date), "08:00", employee=self.emp_a
        )
        self.assertEqual(result, "08:00")

    def test_specific_holiday_with_unassigned_emp_b_unchanged(self):
        """emp_b is NOT in the specific holiday — hour must stay unchanged."""
        result = attendance_day_checking(
            str(self.specific_date), "08:00", employee=self.emp_b
        )
        self.assertEqual(result, "08:00")

    def test_normal_date_always_unchanged(self):
        """Non-holiday date: minimum_hour unchanged regardless of employee."""
        for emp in (None, self.emp_a, self.emp_b):
            with self.subTest(employee=emp):
                result = attendance_day_checking(
                    str(self.normal_date), "08:00", employee=emp
                )
                self.assertEqual(result, "08:00")

"""Tests for Attendance.adjust_minimum_hour() holiday handling."""

from django.test import TestCase

from attendance.models import Attendance
from attendance.tests.fixtures import HolidayFixtureMixin


class TestAttendanceAdjustMinimumHour(HolidayFixtureMixin, TestCase):
    """
    Attendance.adjust_minimum_hour() must set minimum_hour='00:00' and
    is_holiday=True only for holidays applicable to the attendance's employee.
    """

    def _make_attendance(self, employee, att_date, minimum_hour="08:00"):
        """Return an unsaved Attendance instance with required fields set."""
        att = Attendance(
            employee_id=employee,
            attendance_date=att_date,
            shift_id=self.shift,
            attendance_day=self.shift_day,
            minimum_hour=minimum_hour,
            attendance_clock_in_date=att_date,
        )
        return att

    def test_global_holiday_zeroes_every_employee(self):
        for emp in (self.emp_a, self.emp_b):
            with self.subTest(employee=emp):
                att = self._make_attendance(emp, self.global_date)
                att.adjust_minimum_hour()
                self.assertEqual(att.minimum_hour, "00:00")
                self.assertTrue(att.is_holiday)

    def test_specific_holiday_zeroes_assigned_emp_a(self):
        """emp_a is in the specific holiday — must be treated as holiday."""
        att = self._make_attendance(self.emp_a, self.specific_date)
        att.adjust_minimum_hour()
        self.assertEqual(att.minimum_hour, "00:00")
        self.assertTrue(att.is_holiday)

    def test_specific_holiday_does_not_zero_unassigned_emp_b(self):
        """emp_b is NOT in the specific holiday — minimum_hour must stay unchanged."""
        att = self._make_attendance(self.emp_b, self.specific_date)
        att.adjust_minimum_hour()
        self.assertNotEqual(att.minimum_hour, "00:00")
        self.assertFalse(att.is_holiday)

    def test_normal_date_sets_is_holiday_false(self):
        """Non-holiday date: is_holiday must be explicitly set to False."""
        for emp in (self.emp_a, self.emp_b):
            with self.subTest(employee=emp):
                att = self._make_attendance(emp, self.normal_date)
                att.is_holiday = True  # pre-set to confirm the else branch resets it
                att.adjust_minimum_hour()
                self.assertFalse(att.is_holiday)

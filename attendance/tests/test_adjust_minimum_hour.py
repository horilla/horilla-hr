"""Tests for Attendance.adjust_minimum_hour() holiday handling and off-day shift minimum hours."""

from datetime import time

from django.test import TestCase

from attendance.methods.utils import shift_schedule_today
from attendance.models import Attendance
from attendance.tests.fixtures import HolidayFixtureMixin
from base.models import CompanyLeaves, EmployeeShiftDay, EmployeeShiftSchedule


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

    def test_global_holiday_zeroes_emp_a(self):
        att = self._make_attendance(self.emp_a, self.global_date)
        att.adjust_minimum_hour()
        self.assertEqual(att.minimum_hour, "00:00")
        self.assertTrue(att.is_holiday)

    def test_global_holiday_zeroes_emp_b(self):
        att = self._make_attendance(self.emp_b, self.global_date)
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


class TestOffDayMinimumHourFallback(HolidayFixtureMixin, TestCase):
    """
    When an employee reports to duty on an off-day (either no schedule row,
    minimum_working_hour='00:00', or a weekly CompanyLeaves day), the minimum
    hour must fall back to the shift's standard working schedule rather than '00:00'.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.monday, _ = EmployeeShiftDay.objects.get_or_create(day="monday")
        cls.saturday, _ = EmployeeShiftDay.objects.get_or_create(day="saturday")
        cls.sunday, _ = EmployeeShiftDay.objects.get_or_create(day="sunday")

        # Standard working day schedule on Monday (08:30)
        cls.monday_schedule, _ = EmployeeShiftSchedule.objects.update_or_create(
            shift_id=cls.shift,
            day=cls.monday,
            defaults={
                "minimum_working_hour": "08:30",
                "start_time": time(9, 0),
                "end_time": time(17, 30),
            },
        )

        # Off-day schedule on Saturday explicitly set to '00:00'
        cls.saturday_schedule, _ = EmployeeShiftSchedule.objects.update_or_create(
            shift_id=cls.shift,
            day=cls.saturday,
            defaults={
                "minimum_working_hour": "00:00",
                "start_time": None,
                "end_time": None,
            },
        )

        # Ensure Sunday has no schedule row at all for this shift
        EmployeeShiftSchedule.objects.filter(
            shift_id=cls.shift, day=cls.sunday
        ).delete()

    def test_off_day_with_zero_minimum_hour_falls_back_to_shift_hours(self):
        """Saturday has minimum_working_hour='00:00' -> falls back to shift's 08:30."""
        min_hour, start_sec, end_sec = shift_schedule_today(
            day=self.saturday, shift=self.shift
        )
        self.assertEqual(min_hour, "08:30")
        self.assertEqual(start_sec, 9 * 3600)
        self.assertEqual(end_sec, 17 * 3600 + 30 * 60)

    def test_off_day_without_schedule_row_falls_back_to_shift_hours(self):
        """Sunday has no schedule row -> falls back to shift's 08:30."""
        min_hour, start_sec, end_sec = shift_schedule_today(
            day=self.sunday, shift=self.shift
        )
        self.assertEqual(min_hour, "08:30")
        self.assertEqual(start_sec, 9 * 3600)
        self.assertEqual(end_sec, 17 * 3600 + 30 * 60)

    def test_company_leave_off_day_retains_shift_minimum_hour(self):
        """
        Reporting to duty on a weekly off-day (CompanyLeaves) must retain
        the shift's minimum_hour instead of resetting it to '00:00'.
        """
        weekday_str = str(self.normal_date.weekday())
        CompanyLeaves.objects.get_or_create(
            based_on_week=None,
            based_on_week_day=weekday_str,
        )
        att = Attendance(
            employee_id=self.emp_a,
            attendance_date=self.normal_date,
            shift_id=self.shift,
            attendance_day=self.sunday,
            minimum_hour="00:00",
            attendance_worked_hour="09:30",
            attendance_clock_in_date=self.normal_date,
        )
        att.adjust_minimum_hour()
        att.update_attendance_overtime()
        self.assertEqual(att.minimum_hour, "08:30")
        self.assertEqual(att.attendance_overtime, "01:00")

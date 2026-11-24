"""
The Daily Attendance Rate chart counts only who was expected in: employees
with a shift on their working days, less leave, plus whoever came in anyway.
Employees without a shift never pull the rate down.
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
from base.models import EmployeeShift
from horilla.testkit.factories import (
    make_company,
    make_employee,
    make_leave_request,
    make_leave_type,
    make_user,
)
from leave.models import LeaveRequest

MONDAY = date(2026, 10, 5)
TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = (
    MONDAY + timedelta(days=n) for n in range(1, 7)
)


def clock_in(employee, day):
    return Attendance.objects.create(
        employee_id=employee,
        attendance_date=day,
        attendance_clock_in_date=day,
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="00:00",
    )


class TestDailyAttendanceRate(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Daily Rate Ltd")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        shift.company_id.add(company)
        cls.first = make_employee(
            company=company, email="first@rate.test", first_name="First", shift=shift
        )
        cls.second = make_employee(
            company=company, email="second@rate.test", first_name="Second", shift=shift
        )
        # No shift: a salaried manager who never clocks in, and one who sometimes does.
        cls.manager = make_employee(company=company, email="manager@rate.test")
        cls.clocker = make_employee(company=company, email="clocker@rate.test")
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@rate.test", user=cls.boss)
        cls.annual = make_leave_type("Annual")

    def chart(self, from_date=MONDAY, to_date=SUNDAY):
        self.client.force_login(self.boss)
        data = self.client.get(
            reverse("attendance-dashboard-calendar"),
            {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
        ).json()
        return {d["date"]: (d["count"], d["expected"], d["rate"]) for d in data["days"]}

    def take_leave(self, employee, day, half_day=False):
        leave = make_leave_request(
            employee=employee,
            leave_type=self.annual,
            start_date=day,
            end_date=day,
            status="approved",
        )
        if half_day:
            LeaveRequest.objects.filter(id=leave.id).update(
                start_date_breakdown="first_half", end_date_breakdown="first_half"
            )

    def test_only_employees_with_a_shift_are_expected(self):
        clock_in(self.first, MONDAY)
        clock_in(self.second, MONDAY)
        clock_in(self.first, TUESDAY)
        days = self.chart()
        # The managers without a shift are not counted absent.
        self.assertEqual(days[MONDAY.isoformat()], (2, 2, 100.0))
        self.assertEqual(days[TUESDAY.isoformat()], (1, 2, 50.0))
        self.assertEqual(days[WEDNESDAY.isoformat()], (0, 2, 0.0))

    def test_someone_without_a_shift_counts_on_the_days_they_clock_in(self):
        clock_in(self.first, MONDAY)
        clock_in(self.clocker, MONDAY)
        self.assertEqual(self.chart()[MONDAY.isoformat()], (2, 3, 66.7))

    def test_unvalidated_attendance_counts(self):
        """As the Checked In Today card: a clock-in waiting for validation is present."""
        attendance = clock_in(self.first, MONDAY)
        self.assertFalse(attendance.attendance_validated)
        self.assertEqual(self.chart()[MONDAY.isoformat()][0], 1)

    def test_a_day_when_nobody_was_expected_has_no_rate(self):
        days = self.chart()
        self.assertEqual(days[SATURDAY.isoformat()], (0, 0, None))
        self.assertEqual(days[SUNDAY.isoformat()], (0, 0, None))

    def test_coming_in_on_a_day_off_never_goes_over_100(self):
        clock_in(self.first, SATURDAY)
        self.assertEqual(self.chart()[SATURDAY.isoformat()], (1, 1, 100.0))

    def test_days_still_to_come_have_no_rate(self):
        tomorrow = date.today() + timedelta(days=1)
        days = self.chart(tomorrow, tomorrow + timedelta(days=6))
        self.assertTrue(days)
        self.assertEqual(set(days.values()), {(0, 0, None)})

    def test_leave(self):
        clock_in(self.first, MONDAY)
        self.take_leave(self.second, MONDAY)
        # On a full-day leave: not expected, and a clock-in doesn't count.
        self.assertEqual(self.chart()[MONDAY.isoformat()], (1, 1, 100.0))
        clock_in(self.second, MONDAY)
        self.assertEqual(self.chart()[MONDAY.isoformat()], (1, 1, 100.0))

    def test_half_day_leave(self):
        self.take_leave(self.second, MONDAY, half_day=True)
        self.assertEqual(self.chart()[MONDAY.isoformat()], (0, 1, 0.0))
        # In for the other half: present and expected.
        clock_in(self.second, MONDAY)
        self.assertEqual(self.chart()[MONDAY.isoformat()], (1, 2, 50.0))

    def test_weeks_pool_their_days(self):
        """Over 31 days, one bar per week: present / expected employee-days."""
        for day in (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY):
            clock_in(self.first, day)
        clock_in(self.second, MONDAY)
        self.client.force_login(self.boss)
        data = self.client.get(
            reverse("attendance-dashboard-calendar"),
            {"from_date": "2026-10-01", "to_date": "2026-11-15"},
        ).json()
        self.assertEqual(data["aggregate"], "weekly")
        week = next(d for d in data["days"] if d["from_date"] == MONDAY.isoformat())
        self.assertEqual((week["count"], week["expected"], week["rate"]), (6, 10, 60.0))

    def test_a_failing_query_is_logged(self):
        """An empty chart from a broken query reads as "no attendance"; the log is the only trace."""
        with patch(
            "attendance.dashboard._daily_present_expected",
            side_effect=RuntimeError("query failed"),
        ):
            with self.assertLogs("attendance.dashboard", level="ERROR") as logs:
                days = self.chart()
        self.assertEqual(days, {})
        self.assertIn("Daily attendance rate query failed", logs.output[0])

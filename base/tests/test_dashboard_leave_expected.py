"""
Both dashboards treat approved leave the same way: someone on leave today is
not expected in, unless they clock in anyway, so the two attendance rates
agree.
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from attendance.filters import get_checked_in_on
from attendance.models import Attendance, AttendanceLateComeEarlyOut
from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
from employee.models import Employee
from horilla.testkit.factories import (
    make_company,
    make_employee,
    make_leave_request,
    make_leave_type,
    make_user,
)
from leave.models import LeaveRequest


def clock_in(employee):
    return Attendance.objects.create(
        employee_id=employee,
        attendance_date=date.today(),
        attendance_clock_in_date=date.today(),
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="08:00",
    )


class TestDashboardsOnLeave(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Dashboard Leave Ltd")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        shift.company_id.add(company)
        EmployeeShiftSchedule.objects.create(
            shift_id=shift,
            day=EmployeeShiftDay.objects.get(day=date.today().strftime("%A").lower()),
            start_time=time(8, 0),
            end_time=time(16, 0),
            minimum_working_hour="08:00",
        )
        cls.worker = make_employee(
            company=company, email="worker@leave.test", first_name="Worker", shift=shift
        )
        cls.away = make_employee(
            company=company, email="away@leave.test", first_name="Away", shift=shift
        )
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@leave.test", user=cls.boss)
        cls.annual = make_leave_type("Annual")

    def take_leave(self, status="approved", half_day=False):
        leave = make_leave_request(
            employee=self.away,
            leave_type=self.annual,
            start_date=date.today(),
            end_date=date.today(),
            status=status,
        )
        if half_day:
            LeaveRequest.objects.filter(id=leave.id).update(
                start_date_breakdown="first_half", end_date_breakdown="first_half"
            )

    def figures(self):
        """(present, expected, rate) from the main and the Attendance dashboard."""
        self.client.force_login(self.boss)
        main = self.client.get(reverse("dashboard-kpi-data")).json()
        attendance = self.client.get(reverse("attendance-dashboard-kpi")).json()
        return (
            (main["present_today"], main["expected_today"], main["attendance_rate"]),
            (
                attendance["present_today"],
                attendance["expected_employees"],
                attendance["attendance_rate"],
            ),
        )

    def assertBoth(self, expected):
        main, attendance = self.figures()
        self.assertEqual(main, expected)
        self.assertEqual(attendance, expected)

    def test_someone_on_leave_is_not_expected(self):
        clock_in(self.worker)
        for status in ("approved", "cancel_requested"):
            with self.subTest(status=status):
                LeaveRequest.objects.all().delete()
                self.take_leave(status)
                self.assertBoth((1, 1, 100.0))

    def test_a_leave_request_not_yet_approved_changes_nothing(self):
        clock_in(self.worker)
        self.take_leave("requested")
        self.assertBoth((1, 2, 50.0))

    def test_half_day_leave(self):
        clock_in(self.worker)
        self.take_leave(half_day=True)
        # Not in yet: on leave, so not expected (and not "not checked in").
        self.assertBoth((1, 1, 100.0))
        # Came in for the other half: present and expected, never over 100%.
        clock_in(self.away)
        self.assertBoth((2, 2, 100.0))

    def test_full_day_leave_and_a_clock_in_counts_as_leave(self):
        clock_in(self.worker)
        clock_in(self.away)
        self.take_leave()
        self.assertBoth((1, 1, 100.0))

    def test_expected_is_present_plus_not_checked_in(self):
        self.take_leave(half_day=True)
        self.client.force_login(self.boss)
        data = self.client.get(reverse("dashboard-kpi-data")).json()
        if data["week_off_today"]:
            self.skipTest("Nobody is expected in on a weekly off")
        self.assertEqual(
            data["expected_today"], data["present_today"] + data["not_checked_in"]
        )
        self.assertEqual(data["not_checked_in"], 1)  # the worker

    def test_late_and_on_time_count_only_who_is_checked_in(self):
        """
        On time + late = checked in today: someone on a full-day leave who
        clocked in late is on leave, so not late either.
        """
        clock_in(self.worker)
        late = clock_in(self.away)
        # Not objects.create(): the model's save() saves twice, and
        # create()'s force_insert would insert the same row again.
        for kind in ("late_come", "early_out"):
            AttendanceLateComeEarlyOut(attendance_id=late, type=kind).save()
        self.take_leave()
        self.client.force_login(self.boss)
        data = self.client.get(reverse("attendance-dashboard-kpi")).json()
        self.assertEqual(
            (
                data["present_today"],
                data["on_time"],
                data["late_come"],
                data["early_out"],
            ),
            (1, 1, 0, 0),
        )

    def test_checked_in_today_links_to_a_list_that_agrees(self):
        """
        The Attendance dashboard's card links to the employee list's
        checked_in_on filter, like the main dashboard's, which leaves out
        full-day leave too (the attendance list it linked to did not).
        """
        clock_in(self.worker)
        clock_in(self.away)
        self.take_leave()
        self.client.force_login(self.boss)
        data = self.client.get(reverse("attendance-dashboard-kpi")).json()
        listed = get_checked_in_on(Employee.objects.all(), None, date.today())
        self.assertEqual(list(listed), [self.worker])
        self.assertEqual(data["present_today"], listed.count())

        page = self.client.get(reverse("attendance-dashboard")).content.decode()
        self.assertIn(
            reverse("employee-view") + "?checked_in_on=${data.date}&is_active=True",
            page,
        )

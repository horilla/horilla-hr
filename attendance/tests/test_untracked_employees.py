"""
Employees without a shift: never counted absent, but counted when they do
clock in, and still in the charts that count what actually happened.
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from attendance.dashboard import _expected_attendance_days, expected_employee_ids
from attendance.models import Attendance
from base.models import (
    Department,
    EmployeeShift,
    EmployeeShiftDay,
    EmployeeShiftSchedule,
)
from employee.models import Employee
from horilla.testkit.factories import make_company, make_employee, make_user

MONDAY, FRIDAY = date(2026, 10, 5), date(2026, 10, 9)


def clock_in(employee, day, overtime_second=0):
    attendance = Attendance.objects.create(
        employee_id=employee,
        attendance_date=day,
        attendance_clock_in_date=day,
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="00:00",
    )
    if overtime_second:
        Attendance.objects.filter(pk=attendance.pk).update(
            overtime_second=overtime_second,
            attendance_overtime="01:00",
            attendance_validated=True,
        )
    return attendance


class TestEmployeesWithoutAShift(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Shift Test Ltd")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        shift.company_id.add(company)
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            EmployeeShiftSchedule.objects.create(
                shift_id=shift,
                day=EmployeeShiftDay.objects.get(day=day),
                start_time=time(8, 0),
                end_time=time(16, 0),
                minimum_working_hour="08:00",
            )
        cls.office = Department.objects.create(department="Office")
        cls.office.company_id.add(company)
        cls.worker = make_employee(
            company=company, email="worker@shift.test", first_name="Worker", shift=shift
        )
        cls.salaried = make_employee(
            company=company, email="salaried@shift.test", first_name="Salaried"
        )
        cls.clocker = make_employee(
            company=company,
            email="clocker@shift.test",
            first_name="Clocker",
            department=cls.office,
        )
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@shift.test", user=cls.boss)

    def get(self, name, **params):
        self.client.force_login(self.boss)
        return self.client.get(reverse(name), params).json()

    def test_expected_means_a_shift_or_actual_attendance(self):
        employees = Employee.objects.filter(is_active=True)
        self.assertEqual(
            expected_employee_ids(employees, MONDAY, FRIDAY), {self.worker.id}
        )
        clock_in(self.clocker, MONDAY)
        self.assertEqual(
            expected_employee_ids(employees, MONDAY, FRIDAY),
            {self.worker.id, self.clocker.id},
        )
        days = _expected_attendance_days(employees, MONDAY, FRIDAY)
        self.assertEqual(len(days[self.worker.id]), 5)  # Mon-Fri
        self.assertEqual(days[self.clocker.id], [MONDAY])  # only the day attended
        self.assertEqual(days[self.salaried.id], [])

    def test_top_absentees_never_list_employees_without_a_shift(self):
        clock_in(self.clocker, MONDAY)
        absentees = self.get(
            "attendance-dashboard-absentees",
            from_date=MONDAY.isoformat(),
            to_date=FRIDAY.isoformat(),
        )["absentees"]
        names = [row["name"] for row in absentees]
        self.assertIn(self.worker.get_full_name(), names)
        self.assertNotIn(self.salaried.get_full_name(), names)
        self.assertNotIn(self.clocker.get_full_name(), names)

    def test_someone_without_a_shift_who_clocks_in_counts(self):
        """The review's case: they clocked in, so they are present and expected."""
        clock_in(self.clocker, date.today())
        data = self.get("attendance-dashboard-kpi")
        self.assertEqual(data["present_today"], 1)
        self.assertEqual(data["total_employees"], 4)  # headcount: everyone
        self.assertEqual(data["expected_employees"], 2)  # worker + clocker
        self.assertEqual(data["attendance_rate"], 50.0)
        self.assertEqual(data["expected_to_check_in"], 1)  # the worker

    def test_overtime_of_someone_without_a_shift_is_still_charted(self):
        clock_in(self.clocker, MONDAY, overtime_second=3600)
        data = self.get(
            "attendance-dashboard-overtime",
            from_date=MONDAY.isoformat(),
            to_date=FRIDAY.isoformat(),
        )
        self.assertIn("Office", str(data))


class TestManagerScope(TestCase):
    def test_a_manager_sees_only_their_team(self):
        company = make_company("Scope Ltd")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        shift.company_id.add(company)
        manager_user = make_user("manager")
        manager = make_employee(
            company=company, email="manager@scope.test", user=manager_user
        )
        mine = make_employee(company=company, email="mine@scope.test", shift=shift)
        make_employee(company=company, email="other@scope.test", shift=shift)
        mine.employee_work_info.reporting_manager_id = manager
        mine.employee_work_info.save()
        clock_in(mine, date.today())

        self.client.force_login(manager_user)
        data = self.client.get(reverse("attendance-dashboard-kpi")).json()
        self.assertEqual(data["total_employees"], 1)
        self.assertEqual(data["expected_employees"], 1)
        self.assertEqual(data["present_today"], 1)
        self.assertEqual(data["attendance_rate"], 100.0)

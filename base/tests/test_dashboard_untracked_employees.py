"""
Main dashboard: employees without a shift aren't expected to clock in, but
count when they do, with the same definitions as the Attendance dashboard.
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from attendance.filters import get_expected_to_check_in
from attendance.models import Attendance
from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
from employee.models import Employee
from horilla.testkit.factories import make_company, make_employee, make_user


def clock_in(employee):
    Attendance.objects.create(
        employee_id=employee,
        attendance_date=date.today(),
        attendance_clock_in_date=date.today(),
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="08:00",
    )


class TestDashboardWithoutShift(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Dashboard Shift Ltd")
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
            company=company, email="worker@dash.test", first_name="Worker", shift=shift
        )
        cls.salaried = make_employee(
            company=company, email="salaried@dash.test", first_name="Salaried"
        )
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@dash.test", user=cls.boss)

    def get(self, name):
        self.client.force_login(self.boss)
        return self.client.get(reverse(name)).json()

    def test_only_employees_with_a_shift_are_expected(self):
        data = self.get("dashboard-kpi-data")
        self.assertEqual(data["total_employees"], 3)  # headcount: everyone
        self.assertEqual((data["expected_today"], data["absent_today"]), (1, 1))
        self.assertEqual(data["attendance_rate"], 0)

        clock_in(self.worker)
        data = self.get("dashboard-kpi-data")
        self.assertEqual((data["absent_today"], data["attendance_rate"]), (0, 100.0))

    def test_someone_without_a_shift_who_clocks_in_counts(self):
        clock_in(self.salaried)
        data = self.get("dashboard-kpi-data")
        self.assertEqual(data["present_today"], 1)
        self.assertEqual(data["expected_today"], 2)  # worker + salaried
        self.assertEqual(data["absent_today"], 1)  # the worker
        self.assertEqual(data["attendance_rate"], 50.0)

    def test_both_dashboards_count_checked_in_the_same_way(self):
        clock_in(self.worker)
        clock_in(self.salaried)
        main = self.get("dashboard-kpi-data")
        attendance = self.get("attendance-dashboard-kpi")
        self.assertEqual(main["present_today"], attendance["present_today"])
        self.assertEqual(main["present_today"], 2)
        self.assertEqual(main["attendance_rate"], attendance["attendance_rate"])

    def test_the_expected_to_check_in_list_matches(self):
        expected = get_expected_to_check_in(Employee.objects.all(), None, date.today())
        self.assertEqual(list(expected), [self.worker])

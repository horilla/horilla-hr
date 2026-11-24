"""
Attendance % and Absence % count a day as attended only when it was an
expected day: a Saturday worked doesn't make up for a weekday missed.
"""

from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
from base.models import Department, EmployeeShift
from horilla.testkit.factories import make_company, make_employee, make_user

MONDAY = date(2026, 10, 5)
FRIDAY, SATURDAY = MONDAY + timedelta(days=4), MONDAY + timedelta(days=5)


def clock_in(employee, day):
    Attendance.objects.create(
        employee_id=employee,
        attendance_date=day,
        attendance_clock_in_date=day,
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="00:00",
    )


class TestAttendancePercentage(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Percentage Ltd")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        shift.company_id.add(company)
        workshop = Department.objects.create(department="Workshop")
        workshop.company_id.add(company)
        cls.worker = make_employee(
            company=company,
            email="worker@pct.test",
            shift=shift,
            department=workshop,
        )
        # No shift: never expected, so never absent.
        make_employee(company=company, email="manager@pct.test", department=workshop)
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@pct.test", user=cls.boss)

    def rate(self, name):
        self.client.force_login(self.boss)
        data = self.client.get(
            reverse(name),
            {
                "dimension": "department",
                "from_date": MONDAY.isoformat(),
                "to_date": SATURDAY.isoformat(),
            },
        ).json()
        (workshop,) = data["items"]
        return workshop["rate"], workshop["absent_days"], workshop["expected_days"]

    def test_a_saturday_worked_does_not_cancel_a_weekday_missed(self):
        # In Tuesday to Friday and on Saturday; Monday missed.
        for n in range(1, 6):
            clock_in(self.worker, MONDAY + timedelta(days=n))
        self.assertEqual(
            self.rate("attendance-dashboard-absence-percentage"), (20.0, 1, 5)
        )
        self.assertEqual(self.rate("attendance-dashboard-percentage"), (80.0, 1, 5))

    def test_every_weekday_attended(self):
        for n in range(5):
            clock_in(self.worker, MONDAY + timedelta(days=n))
        self.assertEqual(self.rate("attendance-dashboard-percentage"), (100.0, 0, 5))

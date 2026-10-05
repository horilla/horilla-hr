"""
A regularised half day is half present and half absent.

The summary counted the present half and dropped the other, so the day came out
0.5 paid and 0.5 nowhere: paid days plus unpaid days fell short of the month and
the missing half was never taken off pay. A half day that came from the clock
already counted its other half as absent; this makes the regularised one agree.
"""

import datetime

from django.test import TestCase

from attendance.models import AttendanceConflictResolution
from attendance.views.summary import build_monthly_summary
from employee.models import Employee
from horilla.testkit import make_company, make_employee

WEDNESDAY = datetime.date(2026, 9, 2)


class HalfDayResolutionTests(TestCase):
    def setUp(self):
        company = make_company("Half Day Co")
        self.employee = make_employee(company=company, email="half@test.horilla")

    def _row(self, resolution):
        AttendanceConflictResolution.objects.filter(employee_id=self.employee).delete()
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution=resolution
        )
        rows, _total, _totals = build_monthly_summary(
            WEDNESDAY, WEDNESDAY, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]

    def test_a_half_day_is_half_present_and_half_absent(self):
        row = self._row("half_present")
        self.assertEqual(row["present"], 0.5)
        self.assertEqual(row["absent"], 0.5)

    def test_a_full_day_has_nothing_absent(self):
        row = self._row("full_present")
        self.assertEqual(row["present"], 1.0)
        self.assertEqual(row["absent"], 0.0)

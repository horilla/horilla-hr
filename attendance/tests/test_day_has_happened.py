"""A day still to come (day_has_happened) is Upcoming in every view, whatever is on it so far."""

import datetime
from datetime import time
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from attendance.models import Attendance
from attendance.views import summary
from attendance.views.summary import day_has_happened
from employee.models import Employee
from horilla.testkit import make_company, make_employee

DAY = datetime.date(2026, 9, 2)  # a Wednesday


class DayHasHappenedTests(SimpleTestCase):
    def test_today_and_before_have_happened(self):
        today = datetime.date.today()
        self.assertTrue(day_has_happened(today))
        self.assertTrue(day_has_happened(today - datetime.timedelta(days=1)))
        self.assertFalse(day_has_happened(today + datetime.timedelta(days=1)))


class StillToComeTests(TestCase):
    def setUp(self):
        company = make_company("Still To Come Co")
        self.employee = make_employee(company=company, email="stc@test.horilla")
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=time(9, 0),
            attendance_clock_out_date=DAY,
            attendance_clock_out=time(11, 0),
            attendance_worked_hour="02:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def not_yet(self):
        return patch.object(summary, "day_has_happened", lambda day: day < DAY)

    def cell(self):
        context = summary._build_calendar_context(self.employee, DAY, DAY)
        return [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c["date"] == DAY
        ][0], context["cal_summary"]

    def row(self):
        rows, _w, _t = summary.build_monthly_summary(
            DAY, DAY, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]

    def test_a_day_that_has_happened_shows_what_was_worked(self):
        cell, counts = self.cell()
        self.assertEqual(cell["status"], "short")
        self.assertEqual(counts["upcoming"], 0)
        self.assertEqual(self.row()["upcoming_days"], 0)

    def test_a_day_still_to_come_is_upcoming_and_not_counted(self):
        with self.not_yet():
            cell, counts = self.cell()
            row = self.row()
            grid = summary.daily_cell(cell)
        self.assertEqual(cell["status"], "future")
        self.assertEqual(cell["detail"], "")
        self.assertIsNone(cell["ot_kind"])
        self.assertEqual(counts["upcoming"], 1)
        self.assertEqual(counts["absent"], 0)
        self.assertEqual((grid["status"], grid["code"]), ("future", ""))
        self.assertEqual(row["present"], 0)
        self.assertEqual(row["upcoming_days"], 1)

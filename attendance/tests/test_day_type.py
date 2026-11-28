"""How much of a day was worked: one rule (day_type) on one pair of hours (day_hours), in every view."""

import datetime
from datetime import time
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from attendance.models import Attendance
from attendance.views import summary
from attendance.views.summary import day_hours, day_type
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)  # a Wednesday
H = 3600


class DayTypeTests(SimpleTestCase):
    def test_the_rule(self):
        cases = [
            ((8 * H, 8 * H, 0, True), "full"),
            ((7.5 * H, 8 * H, 30 * 60, True), "full"),  # within the grace
            ((4 * H, 8 * H, 0, True), "half"),
            ((3 * H, 8 * H, 0, True), "short"),
            ((3 * H, 8 * H, 0, False), "mo"),  # no clock-out: a missing punch
            ((0, 0, 0, False), "full"),  # nothing required
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(day_type(*args), expected)

    def test_the_hours_are_time_at_work_against_the_minimum(self):
        self.assertEqual(
            day_hours({"at_work_second": 5 * H, "minimum_hour": "08:30"}),
            (5 * H, 8.5 * H),
        )
        self.assertEqual(
            day_hours({"at_work_second": None, "minimum_hour": ""}), (0, 0)
        )


class EveryViewJudgesTheSameHoursTests(TestCase):
    """A 9-hour day judged as 2 of 8 hours by day_hours is short in every view."""

    def setUp(self):
        company = make_company("Day Type Co")
        self.employee = make_employee(company=company, email="dt@test.horilla")
        user = make_user("dt-admin", is_superuser=True)
        make_employee(company=company, email="dt-admin@test.horilla", user=user)
        self.client.force_login(user)
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=time(9, 0),
            attendance_clock_out_date=DAY,
            attendance_clock_out=time(18, 0),
            attendance_worked_hour="09:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )
        self.params = {
            "employee_id": self.employee.pk,
            "from_date": DAY.isoformat(),
            "to_date": DAY.isoformat(),
        }

    def judged_short(self):
        return patch.object(summary, "day_hours", lambda row: (2 * H, 8 * H))

    def views(self):
        rows, _w, _t = summary.build_monthly_summary(
            DAY, DAY, type(self.employee).objects.filter(pk=self.employee.pk)
        )
        calendar = summary._build_calendar_context(self.employee, DAY, DAY)
        cell = [
            c
            for m in calendar["months"]
            for w in m["weeks"]
            for c in w
            if c and c["date"] == DAY
        ][0]
        detail = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {**self.params, "metric": "present"},
            HTTP_HX_REQUEST="true",
        )
        absent = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {**self.params, "metric": "absent"},
            HTTP_HX_REQUEST="true",
        )
        panel = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {**self.params, "date": DAY.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        return {
            "table present": rows[0]["present"],
            "calendar": cell["status"],
            "detail": detail.context["records"][0]["day_type"],
            "absent list": [r["date"] for r in absent.context["records"]],
            "panel": panel.context["day_type"],
        }

    def test_as_recorded_the_day_is_present(self):
        seen = self.views()
        self.assertEqual(seen["table present"], 1)
        self.assertEqual(seen["calendar"], "present")
        self.assertEqual(seen["detail"], "full")
        self.assertEqual(seen["absent list"], [])
        self.assertEqual(seen["panel"], "full")

    def test_judged_short_the_day_is_short_everywhere(self):
        with self.judged_short():
            seen = self.views()
        self.assertEqual(seen["table present"], 0)
        self.assertEqual(seen["calendar"], "short")
        self.assertEqual(seen["detail"], "short")
        self.assertEqual(seen["absent list"], [DAY])
        self.assertEqual(seen["panel"], "short")

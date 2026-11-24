"""The Attendances lists' Attendance Status column shows each day the way the
Attendance Status filter picks it: On Time or Late Arrival, and Early
Departure."""

import datetime
import re
from importlib import import_module

from django.conf import settings
from django.test import RequestFactory, TestCase
from django.urls import reverse

from attendance.cbv.attendances import AttendancesListView
from attendance.models import AttendanceLateComeEarlyOut
from horilla import horilla_middlewares
from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_attendance

DAY = datetime.date(2026, 11, 24)


def badges(html):
    text = re.sub(r"<[^>]+>", " ", str(html))
    return [
        label
        for label in ("On Time", "Late Arrival", "Early Departure")
        if label in " ".join(text.split())
    ]


class AttendanceStatusColumnTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Status Column Co")
        cls.user = make_user("status-column-admin", is_superuser=True)
        make_employee(
            company=company, email="status-column-admin@test.horilla", user=cls.user
        )
        cls.days = {}
        for name, kinds in (
            ("prompt", []),
            ("tardy", ["late_come"]),
            ("leaver", ["early_out"]),
            ("both", ["late_come", "early_out"]),
        ):
            employee = make_employee(company=company, email=f"{name}@test.horilla")
            attendance = make_attendance(employee=employee, attendance_date=DAY)
            for kind in kinds:
                AttendanceLateComeEarlyOut(attendance_id=attendance, type=kind).save()
            cls.days[name] = attendance

    def cell(self, name):
        # render_template reads the request Horilla's middleware keeps.
        request = RequestFactory().get("/")
        request.session = import_module(settings.SESSION_ENGINE).SessionStore()
        request.session.save()
        request.user = self.user
        horilla_middlewares._thread_locals.request = request
        try:
            return badges(self.days[name].attendance_status_col())
        finally:
            horilla_middlewares._thread_locals.request = None

    def test_each_kind_of_day(self):
        self.assertEqual(self.cell("prompt"), ["On Time"])
        self.assertEqual(self.cell("tardy"), ["Late Arrival"])
        self.assertEqual(self.cell("leaver"), ["On Time", "Early Departure"])
        self.assertEqual(self.cell("both"), ["Late Arrival", "Early Departure"])

    def test_shown_by_default_after_check_out(self):
        fields = [column[1] for column in AttendancesListView.default_columns]
        self.assertEqual(
            fields[fields.index("attendance_clock_out") + 1], "attendance_status_col"
        )

    def test_the_validated_list_shows_it(self):
        self.client.force_login(self.user)
        page = self.client.get(
            reverse("validated-attendance-tab"), HTTP_HX_REQUEST="true"
        )
        self.assertContains(page, "Attendance Status")
        self.assertContains(page, "attendance-status-badge--late", count=2)

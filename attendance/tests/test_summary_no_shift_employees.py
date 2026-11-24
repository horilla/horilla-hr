"""The monthly summary lists employees with a shift, plus anyone without one who attended."""

import datetime
import io
from datetime import time

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
from base.models import EmployeeShift
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)  # a Wednesday


class SummaryNoShiftEmployeesTests(TestCase):
    def setUp(self):
        company = make_company("No Shift Co")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        self.worker = make_employee(
            company=company,
            email="worker@test.horilla",
            first_name="Worker",
            shift=shift,
        )
        self.manager = make_employee(
            company=company, email="manager@test.horilla", first_name="Manager"
        )
        user = make_user("hr-no-shift", is_superuser=True)
        make_employee(company=company, email="hr@no-shift.test", user=user)
        self.client.force_login(user)

    def listed(self, view, **extra):
        response = self.client.get(
            reverse("attendance-monthly-summary-table"),
            {
                "view": view,
                "from_date": DAY.isoformat(),
                "to_date": DAY.isoformat(),
                **extra,
            },
            HTTP_HX_REQUEST="true",
        )
        return {row["employee"].pk for row in response.context["rows"]}

    def exported(self, **extra):
        from openpyxl import load_workbook

        response = self.client.get(
            reverse("attendance-monthly-summary-export"),
            {"from_date": DAY.isoformat(), "to_date": DAY.isoformat(), **extra},
        )
        sheet = load_workbook(io.BytesIO(response.content)).active
        return " ".join(str(c.value) for row in sheet.iter_rows() for c in row)

    def attend(self, employee):
        Attendance.objects.create(
            employee_id=employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=time(9, 0),
            attendance_clock_out_date=DAY,
            attendance_clock_out=time(17, 0),
            attendance_worked_hour="08:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def test_someone_without_a_shift_who_never_attended_is_left_out(self):
        for view in ("list", "daily"):
            with self.subTest(view=view):
                listed = self.listed(view)
                self.assertIn(self.worker.pk, listed)
                self.assertNotIn(self.manager.pk, listed)
        self.assertIn("Worker", self.exported())
        self.assertNotIn("Manager", self.exported())

    def test_someone_without_a_shift_who_attended_is_listed(self):
        self.attend(self.manager)
        for view in ("list", "daily"):
            with self.subTest(view=view):
                self.assertIn(self.manager.pk, self.listed(view))
        self.assertIn("Manager", self.exported())

    def test_someone_picked_by_name_is_listed_whatever_their_shift(self):
        self.assertEqual(
            self.listed("list", employee_id=self.manager.pk), {self.manager.pk}
        )
        self.assertIn("Manager", self.exported(employee_id=self.manager.pk))
        self.assertIn("Manager", self.exported(employee_ids=self.manager.pk))

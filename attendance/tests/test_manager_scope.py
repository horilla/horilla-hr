"""A reporting manager can only validate or approve their own reports' attendance.

``manager_can_enter`` lets in anyone who manages *any* employee, so each route that
acts on a record named in the request has to check that record's employee itself.
Covers the single and bulk validate routes and the single and bulk overtime approve
routes.
"""

import json
from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from attendance.models import Attendance
from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_attendance


class ManagerScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Scope Co")
        cls.users = {}
        cls.people = {}
        for key in ("mgr_a", "mgr_b", "emp_a", "emp_b"):
            user = make_user(f"scope_{key}", password="secret123")
            cls.users[key] = user
            cls.people[key] = make_employee(
                company=company,
                email=f"{key}@scope.test",
                first_name=key,
                last_name="Scope",
                user=user,
            )
        for emp, mgr in (("emp_a", "mgr_a"), ("emp_b", "mgr_b")):
            work_info = cls.people[emp].employee_work_info
            work_info.reporting_manager_id = cls.people[mgr]
            work_info.save()

    def setUp(self):
        day = date.today() - timedelta(days=1)
        self.att_a = make_attendance(
            employee=self.people["emp_a"],
            attendance_date=day,
            overtime_second=3600,
            validated=False,
        )
        self.att_b = make_attendance(
            employee=self.people["emp_b"],
            attendance_date=day,
            overtime_second=3600,
            validated=False,
        )
        # The factory marks overtime approved up front; start from pending.
        Attendance.objects.filter(pk__in=[self.att_a.pk, self.att_b.pk]).update(
            attendance_overtime_approve=False
        )

    def _client(self, key):
        client = Client()
        client.force_login(type(self.users[key]).objects.get(pk=self.users[key].pk))
        return client

    def _fresh(self, attendance):
        return Attendance.objects.get(pk=attendance.pk)

    # -- validate one -------------------------------------------------------

    def test_manager_validates_their_own_report(self):
        self._client("mgr_a").get(
            reverse("validate-this-attendance", args=[self.att_a.pk])
        )
        self.assertTrue(self._fresh(self.att_a).attendance_validated)

    def test_manager_cannot_validate_someone_elses_report(self):
        self._client("mgr_a").get(
            reverse("validate-this-attendance", args=[self.att_b.pk])
        )
        self.assertFalse(self._fresh(self.att_b).attendance_validated)

    # -- validate many ------------------------------------------------------

    def test_bulk_validate_skips_records_outside_the_managers_reports(self):
        self._client("mgr_a").post(
            reverse("validate-bulk-attendance"),
            {"ids": json.dumps([self.att_a.pk, self.att_b.pk])},
        )
        self.assertTrue(self._fresh(self.att_a).attendance_validated)
        self.assertFalse(self._fresh(self.att_b).attendance_validated)

    # -- approve overtime ---------------------------------------------------

    def test_manager_approves_their_own_reports_overtime(self):
        self._client("mgr_a").get(reverse("approve-overtime", args=[self.att_a.pk]))
        self.assertTrue(self._fresh(self.att_a).attendance_overtime_approve)

    def test_manager_cannot_approve_someone_elses_reports_overtime(self):
        self._client("mgr_a").get(reverse("approve-overtime", args=[self.att_b.pk]))
        self.assertFalse(self._fresh(self.att_b).attendance_overtime_approve)

    def test_bulk_overtime_skips_records_outside_the_managers_reports(self):
        self._client("mgr_a").post(
            reverse("approve-bulk-overtime"),
            {"ids": json.dumps([self.att_a.pk, self.att_b.pk])},
        )
        self.assertTrue(self._fresh(self.att_a).attendance_overtime_approve)
        self.assertFalse(self._fresh(self.att_b).attendance_overtime_approve)

    # -- the permission still covers everyone ----------------------------------

    def test_change_attendance_permission_covers_every_employee(self):
        mgr = self.users["mgr_a"]
        mgr.user_permissions.add(Permission.objects.get(codename="change_attendance"))
        self._client("mgr_a").post(
            reverse("validate-bulk-attendance"),
            {"ids": json.dumps([self.att_a.pk, self.att_b.pk])},
        )
        self.assertTrue(self._fresh(self.att_a).attendance_validated)
        self.assertTrue(self._fresh(self.att_b).attendance_validated)

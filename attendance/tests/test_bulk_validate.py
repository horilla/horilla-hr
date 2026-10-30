"""Bulk validate reports how many attendances it validated (X-Hlv-Bulk-Result)
so the browser can show the shared progress + result dialog."""

import datetime
import json

from django.test import Client, TestCase
from django.urls import reverse

from attendance.models import Attendance
from horilla.testkit import make_company, make_employee, make_user


class BulkAttendanceMixin:
    """Shared fixtures and helpers; mixed into each test class so every test runs once."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        company = make_company("Validate Co")
        cls.user = make_user("validate-admin", is_superuser=True)
        make_employee(
            company=company, email="validate-admin@test.horilla", user=cls.user
        )
        cls.staff = make_employee(company=company, email="validate-staff@test.horilla")

    def _attendance(self, days_ago, **extra):
        date = datetime.date.today() - datetime.timedelta(days=days_ago)
        fields = dict(
            employee_id=self.staff,
            attendance_date=date,
            attendance_clock_in_date=date,
            attendance_clock_in=datetime.time(9, 0),
            attendance_clock_out_date=date,
            attendance_clock_out=datetime.time(18, 0),
            attendance_worked_hour="09:00",
            at_work_second=9 * 3600,
            minimum_hour="08:00",
        )
        fields.update(extra)
        return Attendance.objects.create(**fields)

    def _post(self, ids):
        client = Client()
        client.force_login(self.user)
        response = client.post(
            reverse("validate-bulk-attendance"), {"ids": json.dumps(ids)}
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response["X-Hlv-Bulk-Result"])


class BulkValidateAttendanceTests(BulkAttendanceMixin, TestCase):
    def test_counts_validated_and_failed(self):
        ok, pending = self._attendance(1), self._attendance(2, is_validate_request=True)

        result = self._post([ok.pk, pending.pk, 999999])

        ok.refresh_from_db()
        pending.refresh_from_db()
        self.assertTrue(ok.attendance_validated)
        self.assertFalse(pending.attendance_validated)
        self.assertEqual(result, {"done": 1, "failed": 2})


class BulkApproveOvertimeTests(BulkAttendanceMixin, TestCase):
    def test_counts_approved_and_failed(self):
        pending = self._attendance(1, at_work_second=10 * 3600, overtime_second=7200)
        already = self._attendance(2, attendance_overtime_approve=True)

        client = Client()
        client.force_login(self.user)
        response = client.post(
            reverse("approve-bulk-overtime"),
            {"ids": json.dumps([pending.pk, already.pk, 999999])},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response["X-Hlv-Bulk-Result"]), {"done": 1, "failed": 2}
        )
        pending.refresh_from_db()
        self.assertTrue(pending.attendance_overtime_approve)


class BulkAttendanceRequestTests(BulkAttendanceMixin, TestCase):
    """Bulk approve / reject of attendance requests report their counts."""

    def _post_request_action(self, url_name, ids):
        client = Client()
        client.force_login(self.user)
        response = client.post(reverse(url_name), {"ids": json.dumps(ids)})
        self.assertEqual(response.status_code, 200)
        return json.loads(response["X-Hlv-Bulk-Result"])

    def test_reject_counts_pending_requests_only(self):
        pending = self._attendance(1, is_validate_request=True)
        processed = self._attendance(2)

        result = self._post_request_action(
            "bulk-reject-attendance-request", [pending.pk, processed.pk, 999999]
        )

        pending.refresh_from_db()
        self.assertFalse(pending.is_validate_request)
        self.assertEqual(result, {"done": 1, "failed": 2})

    def test_approve_skips_missing_and_already_processed(self):
        processed = self._attendance(1)

        result = self._post_request_action(
            "bulk-approve-attendance-request", [processed.pk, 999999]
        )

        self.assertEqual(result, {"done": 0, "failed": 2})

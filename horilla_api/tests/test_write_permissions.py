"""Admin/manager-level API writes are gated; self-service creates bind to the caller."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from base.models import EmployeeShift
from employee.models import ProfileEditFeature
from horilla.testkit import make_company, make_employee, make_user


class WritePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        company = make_company("API Perm Co")
        self.user = make_user("api_perm_emp", password="secret123")
        self.employee = make_employee(
            company=company, email="api_perm_emp@test.horilla", user=self.user
        )
        self.other = make_employee(company=company, email="api_perm_other@test.horilla")
        self.client.force_authenticate(user=self.user)

    def test_plain_employee_cannot_delete_asset(self):
        response = self.client.delete("/api/asset/assets/999")
        self.assertEqual(response.status_code, 401)  # house permission_required

    def test_plain_employee_cannot_approve_asset_request(self):
        response = self.client.put("/api/asset/asset-approve/999")
        self.assertEqual(response.status_code, 401)

    def test_plain_employee_cannot_validate_attendance(self):
        response = self.client.put("/api/attendance/attendance-validate/999")
        self.assertEqual(response.status_code, 403)  # manager_permission_required

    def test_plain_employee_cannot_list_mail_templates(self):
        response = self.client.get("/api/attendance/mail-templates")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_read_tax_brackets(self):
        response = self.client.get("/api/payroll/tax-bracket/")
        self.assertNotEqual(response.status_code, 200)

    def test_shift_request_binds_to_caller_and_ignores_approval_flags(self):
        shift = EmployeeShift.objects.create(employee_shift="Perm Shift")
        response = self.client.post(
            "/api/base/shift-requests/",
            {
                "employee_id": self.other.id,
                "shift_id": shift.id,
                "requested_date": date.today().isoformat(),
                "is_permanent_shift": True,
                "approved": True,
                "canceled": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee_id"], self.employee.id)
        self.assertFalse(response.data["approved"])
        self.assertFalse(response.data["canceled"])

    def test_employee_cannot_rebind_login(self):
        # Self-edit now honours the profile-edit switch, as the web UI does,
        # and a missing row reads as "off". Turn it on so this test exercises
        # the login-rebind protection rather than the toggle.
        ProfileEditFeature.objects.create(is_enabled=True)
        response = self.client.put(
            f"/api/employee/employees/{self.employee.id}/",
            {"employee_user_id": self.other.employee_user_id.id},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.employee_user_id, self.user)

    def test_login_missing_credentials_is_400(self):
        response = APIClient().post("/api/auth/login/", {"username": "x"})
        self.assertEqual(response.status_code, 400)

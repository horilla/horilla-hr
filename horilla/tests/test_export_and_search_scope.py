"""Client-supplied field paths cannot reach bank, payroll or credential data.

The generic export and the shared filter's ``search_field`` both take a field path
from the browser. Both go through ``_export_part_allowed``.
"""

import json

from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from employee.models import Employee, EmployeeBankDetails
from horilla.filters import HorillaFilterSet
from horilla.horilla_middlewares import _thread_locals
from horilla.testkit import make_company, make_employee, make_user
from horilla_views.views import _export_part_allowed

ACCOUNT = "ACCT-55501234"


class ExportAndSearchScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Fields Co")
        cls.user = make_user("fields_user", password="secret123")
        cls.person = make_employee(
            company=company,
            email="fields@scope.test",
            first_name="Fields",
            last_name="Person",
            user=cls.user,
        )
        EmployeeBankDetails.objects.create(
            employee_id=cls.person, bank_name="Test Bank", account_number=ACCOUNT
        )

    def _grant(self, codename):
        self.user.user_permissions.add(Permission.objects.get(codename=codename))
        return type(self.user).objects.get(pk=self.user.pk)

    def _export_text(self, user):
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("export-list", args=["fields"]) + "?model=employee.Employee",
            {
                "ids": json.dumps([self.person.pk]),
                "columns": json.dumps(
                    [
                        ["Name", "employee_first_name"],
                        ["Account", "employee_bank_details__account_number"],
                    ]
                ),
                "format": "csv",
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8", errors="ignore")

    # -- export -------------------------------------------------------------

    def test_part_rules(self):
        user = type(self.user).objects.get(pk=self.user.pk)
        for part in ("account_number", "bank_name", "employee_bank_details", "net_pay"):
            self.assertFalse(_export_part_allowed(user, part), part)
        for part in ("password", "_meta", "otp"):
            self.assertFalse(_export_part_allowed(user, part), part)
        for part in ("employee_first_name", "email", "job_position_id"):
            self.assertTrue(_export_part_allowed(user, part), part)

    def test_permission_opens_the_financial_parts(self):
        user = self._grant("view_employeebankdetails")
        self.assertTrue(_export_part_allowed(user, "account_number"))
        self.assertFalse(_export_part_allowed(user, "net_pay"))

    def test_export_blanks_bank_details_without_the_permission(self):
        user = type(self.user).objects.get(pk=self.user.pk)
        text = self._export_text(user)
        self.assertIn("Fields", text)
        self.assertNotIn(ACCOUNT, text)

    def test_export_includes_bank_details_with_the_permission(self):
        text = self._export_text(self._grant("view_employeebankdetails"))
        self.assertIn(ACCOUNT, text)

    # -- search_field -------------------------------------------------------

    def _safe(self, path):
        request = RequestFactory().get("/")
        request.user = type(self.user).objects.get(pk=self.user.pk)
        _thread_locals.request = request
        try:
            return HorillaFilterSet._is_safe_search_path(Employee, path)
        finally:
            _thread_locals.request = None

    def test_search_field_refuses_credentials_and_financial_paths(self):
        for path in (
            "employee_user_id__password",
            "employee_bank_details__account_number",
            "delete",
        ):
            self.assertFalse(self._safe(path), path)

    def test_search_field_allows_plain_field_paths(self):
        for path in ("employee_first_name", "employee_work_info__email"):
            self.assertTrue(self._safe(path), path)

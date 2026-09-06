"""
Quick-export column paths are client-supplied attribute walks. They must not
be able to reach credentials through relations (employee_user_id__password).
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user


class ExportColumnPathTests(TestCase):
    def setUp(self):
        company = make_company("Export Corp")
        self.admin = make_user(
            "export_admin", is_superuser=True, password="pw-not-real"
        )
        make_employee(company=company, email="admin@test.horilla", user=self.admin)
        self.target = make_employee(
            company=company, email="target@test.horilla", first_name="Targeted"
        )
        self.client.force_login(self.admin)
        self.client.session["selected_company"] = str(company.pk)

    def _export(self, columns):
        url = (
            reverse("export-list", kwargs={"short_id": "abc"})
            + "?model=employee.Employee"
        )
        return self.client.post(
            url,
            {"ids": str([self.target.pk]), "columns": str(columns), "format": "csv"},
        )

    def test_credential_paths_are_blanked(self):
        response = self._export(
            [["Name", "employee_first_name"], ["Pw", "employee_user_id__password"]]
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode(errors="ignore")
        self.assertIn("Targeted", body)
        self.assertNotIn(self.target.employee_user_id.password, body)
        self.assertNotIn("pbkdf2", body)

    def test_private_attributes_are_blanked(self):
        response = self._export([["State", "_state__db"]])
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "default",
            (
                response.content.decode(errors="ignore").split("\n")[1:][0]
                if response.content.count(b"\n")
                else ""
            ),
        )

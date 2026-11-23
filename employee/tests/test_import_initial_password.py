"""employee-import/ must not set a new login's password to the employee's phone number."""

import io

import pandas as pd
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user
from horilla_auth.models import HorillaUser

PHONE = "5551234567"
EMAIL = "imported.person@test.horilla"


def _sheet(rows):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return SimpleUploadedFile(
        "employees.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class EmployeeImportInitialPasswordTests(TestCase):
    def setUp(self):
        company = make_company("Import Co")
        self.actor = make_user("importer")
        make_employee(company=company, email="importer@test.horilla", user=self.actor)
        self.actor.user_permissions.add(Permission.objects.get(codename="add_employee"))
        self.client.force_login(self.actor)
        self.url = reverse("employee-import")

    def _import(self, phone=PHONE, email=EMAIL):
        return self.client.post(
            self.url,
            {
                "file": _sheet(
                    [
                        {
                            "employee_full_name": "Imported Person",
                            "email": email,
                            "phone": phone,
                        }
                    ]
                )
            },
        )

    def test_import_still_creates_the_employee_and_login(self):
        self._import()
        user = HorillaUser.objects.get(username=EMAIL)
        self.assertTrue(Employee.objects.filter(employee_user_id=user).exists())

    def test_phone_number_is_not_the_password(self):
        self._import()
        user = HorillaUser.objects.get(username=EMAIL)
        self.assertFalse(user.check_password(PHONE))

    def test_each_imported_login_gets_its_own_password(self):
        self._import(email="one@test.horilla")
        self._import(email="two@test.horilla")
        one = HorillaUser.objects.get(username="one@test.horilla")
        two = HorillaUser.objects.get(username="two@test.horilla")
        self.assertNotEqual(one.password, two.password)

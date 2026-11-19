"""An employee's email is optional.

Not everyone Horilla holds a record for signs in or reads mail from it, and
an email is not always known when someone is added. No email is stored as
NULL, so any number of employees can be without one, and everything that
reads the address copes with it missing.
"""

import pandas as pd
from django.test import TestCase
from django.urls import reverse

from base.models import EmailLog
from employee.forms import EmployeeForm
from employee.methods.methods import (
    bulk_create_employee_import,
    bulk_create_user_import,
    process_employee_records,
    send_employee_invitation,
)
from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user


class EmployeeWithoutEmailTests(TestCase):
    def setUp(self):
        self.company = make_company("Co")

    def test_an_employee_without_an_email_gets_a_login_with_a_random_username(self):
        employee = Employee.objects.create(employee_first_name="Sam")
        employee.refresh_from_db()
        self.assertIsNone(employee.email)
        user = employee.employee_user_id
        self.assertIsNotNone(user)
        self.assertEqual(len(user.username), 5)
        self.assertEqual(user.email, "")

    def test_any_number_of_employees_can_have_no_email(self):
        Employee.objects.create(employee_first_name="Sam")
        Employee.objects.create(employee_first_name="Alex", email="")
        self.assertEqual(Employee.objects.entire().filter(email=None).count(), 2)
        self.assertFalse(Employee.objects.entire().filter(email="").exists())

    def test_adding_an_email_later_keeps_the_username(self):
        employee = Employee.objects.create(employee_first_name="Sam")
        username = employee.employee_user_id.username
        employee.email = "sam@test.horilla"
        employee.save()
        employee.employee_user_id.refresh_from_db()
        self.assertEqual(employee.employee_user_id.username, username)

    def test_the_mail_helpers_give_nothing_rather_than_none_text(self):
        employee = make_employee(company=self.company, email="")
        EmailLog.objects.create(
            subject="Hello",
            from_email="hr@test.horilla",
            to="someone@test.horilla",
            body="body",
            status="sent",
        )
        self.assertIsNone(employee.get_mail())
        self.assertEqual(employee.get_email(), "")
        self.assertIsNone(employee.get_last_sent_mail())

    def test_no_invitation_is_claimed_without_an_email(self):
        employee = make_employee(company=self.company, email="")
        self.assertFalse(send_employee_invitation(employee, "testserver", False))


class EmployeeFormEmailTests(TestCase):
    def test_the_form_accepts_no_email(self):
        form = EmployeeForm(
            data={"employee_first_name": "Sam", "badge_id": "S-1", "email": ""}
        )
        self.assertFalse(form.fields["email"].required)
        self.assertNotIn("email", form.errors)

    def test_an_invalid_email_is_a_form_error_not_a_crash(self):
        form = EmployeeForm(
            data={"employee_first_name": "Sam", "badge_id": "S-1", "email": "nope"}
        )
        self.assertIn("email", form.errors)

    def test_a_taken_email_is_still_refused(self):
        make_employee(company=make_company("Co"), email="sam@test.horilla")
        form = EmployeeForm(
            data={
                "employee_first_name": "Sam",
                "badge_id": "S-1",
                "email": "sam@test.horilla",
            }
        )
        self.assertIn("email", form.errors)


class MailLogWithoutEmailTests(TestCase):
    def setUp(self):
        company = make_company("Co")
        self.admin = make_user("admin", is_superuser=True)
        make_employee(company=company, email="admin@test.horilla", user=self.admin)
        self.employee = make_employee(company=company, email="")
        EmailLog.objects.create(
            subject="For someone else",
            from_email="hr@test.horilla",
            to="someone@test.horilla",
            body="body",
            status="sent",
        )
        self.client.force_login(self.admin)

    def test_the_mail_log_tab_is_empty(self):
        response = self.client.get(
            reverse("individual-email-log-list", kwargs={"pk": self.employee.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "For someone else")

    def test_the_mail_log_is_empty(self):
        response = self.client.get(
            reverse("employee-get-mail-log", kwargs={"pk": self.employee.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "For someone else")


class EmployeeImportWithoutEmailTests(TestCase):
    def row(self, **extra):
        return {
            "Badge ID": "B-1",
            "First Name": "Sam",
            "Last Name": "Lee",
            "Phone": "9876543210",
            "Email": None,
            "Gender": None,
            **extra,
        }

    def test_a_row_without_an_email_is_imported_with_the_badge_id_as_username(self):
        frame = pd.DataFrame([self.row(), self.row(**{"Badge ID": "B-2"})])
        frame = frame.astype(object).where(pd.notnull(frame), None)
        success, errors, _count = process_employee_records(frame, None)
        self.assertEqual(errors, [])
        bulk_create_user_import(success)
        employees = bulk_create_employee_import(success)
        self.assertEqual(len(employees), 2)
        for badge_id in ("B-1", "B-2"):
            employee = Employee.objects.entire().get(badge_id=badge_id)
            self.assertIsNone(employee.email)
            self.assertEqual(employee.employee_user_id.username, badge_id)
            self.assertEqual(employee.employee_user_id.email, "")

    def test_a_bad_email_is_still_an_error(self):
        frame = pd.DataFrame([self.row(Email="nope")])
        success, errors, _count = process_employee_records(frame, None)
        self.assertEqual(success, [])
        self.assertIn("Email Error", errors[0])

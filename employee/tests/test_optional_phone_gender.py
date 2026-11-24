"""Phone and gender are optional on an employee.

Neither is needed to run Horilla for someone: the model already saved
employees without them (imports leave gender empty, the terminal and LDAP
paths save an empty phone), only the form insisted. Gender also defaulted to
"male", so anyone added without one was recorded as male.
"""

from django.test import TestCase

from employee.forms import EmployeeForm
from employee.models import Employee
from horilla.testkit import make_company


class OptionalPhoneGenderTests(TestCase):
    def test_the_employee_form_accepts_no_phone_and_no_gender(self):
        form = EmployeeForm(
            data={
                "employee_first_name": "Sam",
                "email": "sam@test.horilla",
                "badge_id": "S-1",
            }
        )
        self.assertNotIn("phone", form.errors)
        self.assertNotIn("gender", form.errors)
        self.assertFalse(form.fields["phone"].required)
        self.assertFalse(form.fields["gender"].required)

    def test_an_employee_saved_without_a_gender_is_not_recorded_as_male(self):
        make_company("Co")
        employee = Employee.objects.create(
            employee_first_name="Sam", email="sam@test.horilla"
        )
        employee.refresh_from_db()
        self.assertIsNone(employee.gender)
        self.assertEqual(employee.phone, "")

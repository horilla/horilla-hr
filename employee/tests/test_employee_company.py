"""Employee create + company isolation smoke tests."""

from django.test import TestCase

from employee.models import Employee
from horilla.testkit import CompanyFilterTestMixin, make_company, make_employee


class EmployeeCreateTests(TestCase):
    def test_create_employee_creates_user_and_work_info(self):
        company = make_company("Emp Co")
        emp = make_employee(
            company=company,
            email="newhire@test.horilla",
            first_name="New",
            last_name="Hire",
            phone="9111111111",
        )
        self.assertIsNotNone(emp.pk)
        self.assertTrue(hasattr(emp, "employee_work_info"))
        self.assertEqual(emp.employee_work_info.company_id_id, company.pk)
        self.assertIsNotNone(emp.employee_user_id_id)
        self.assertEqual(emp.employee_user_id.email, "newhire@test.horilla")


class EmployeeCompanyIsolationTests(CompanyFilterTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = make_company("Company A")
        cls.company_b = make_company(
            "Company B",
            address="2 Other St",
            city="SF",
            zip="94105",
        )
        cls.emp_a = make_employee(
            company=cls.company_a,
            email="a@emp.test",
            first_name="Ann",
            last_name="A",
        )
        cls.emp_b = make_employee(
            company=cls.company_b,
            email="b@emp.test",
            first_name="Bob",
            last_name="B",
        )

    def test_company_a_sees_only_own_employees(self):
        self.set_company_context(self.company_a.pk)
        visible = list(Employee.objects.all())
        self.assertIn(self.emp_a, visible)
        self.assertNotIn(self.emp_b, visible)

    def test_company_b_sees_only_own_employees(self):
        self.set_company_context(self.company_b.pk)
        visible = list(Employee.objects.all())
        self.assertNotIn(self.emp_a, visible)
        self.assertIn(self.emp_b, visible)

    def test_entire_bypasses_company_filter(self):
        self.set_company_context(self.company_a.pk)
        all_rows = list(Employee.objects.entire())
        self.assertIn(self.emp_a, all_rows)
        self.assertIn(self.emp_b, all_rows)

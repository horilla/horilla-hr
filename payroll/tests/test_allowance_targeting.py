from datetime import date

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.component_engine import eligible_allowances
from payroll.models.models import Allowance

START, END = date(2026, 11, 1), date(2026, 11, 30)


class IncludeAllTests(TestCase):
    """Who an allowance reaches when a payslip is calculated."""

    def setUp(self):
        self.company = make_company("Targeting Co")
        self.existing = make_employee(company=self.company, email="old@test.horilla")

    def _allowance(self, title, **fields):
        return Allowance.objects.create(
            title=title, is_fixed=True, amount=100, **fields
        )

    def _eligible(self, employee):
        return set(eligible_allowances(employee, START, END))

    def test_new_joiners_get_an_include_all_allowance_without_being_added(self):
        everyone = self._allowance("Everyone", include_active_employees=True)
        joiner = make_employee(company=self.company, email="new@test.horilla")
        self.assertIn(everyone, self._eligible(joiner))

    def test_an_excluded_employee_is_left_out_of_include_all(self):
        everyone = self._allowance("Everyone", include_active_employees=True)
        everyone.exclude_employees.add(self.existing)
        self.assertNotIn(everyone, self._eligible(self.existing))

    def test_selected_only_is_the_default_and_skips_new_joiners(self):
        picked = self._allowance("Picked")
        self.assertFalse(picked.include_active_employees)
        picked.specific_employees.add(self.existing)
        joiner = make_employee(company=self.company, email="new2@test.horilla")
        self.assertIn(picked, self._eligible(self.existing))
        self.assertNotIn(picked, self._eligible(joiner))


class GroupTargetingTests(TestCase):
    """An allowance aimed at a department, job position or job role."""

    def setUp(self):
        from base.models import Department, JobPosition, JobRole

        self.company = make_company("Group Co")
        self.sales = Department.objects.create(department="Sales Group")
        self.support = Department.objects.create(department="Support Group")
        self.lead = JobPosition.objects.create(
            job_position="Team Lead", department_id=self.sales
        )
        self.role = JobRole.objects.create(job_role="Closer", job_position_id=self.lead)

    def _employee(self, email, department=None, position=None, role=None):
        employee = make_employee(
            company=self.company, email=email, department=department
        )
        info = employee.employee_work_info
        info.job_position_id = position
        info.job_role_id = role
        info.save()
        return employee

    def _allowance(self, title, by, **links):
        allowance = Allowance.objects.create(
            title=title, is_fixed=True, amount=100, apply_by=by
        )
        for field, values in links.items():
            getattr(allowance, field).add(*values)
        return allowance

    def _eligible(self, employee):
        return set(eligible_allowances(employee, START, END))

    def test_a_department_allowance_reaches_its_members_and_new_joiners(self):
        bonus = self._allowance(
            "Sales Bonus", "department", apply_departments=[self.sales]
        )
        member = self._employee("s1@test.horilla", department=self.sales)
        outsider = self._employee("o1@test.horilla", department=self.support)
        joiner = self._employee("s2@test.horilla", department=self.sales)
        self.assertIn(bonus, self._eligible(member))
        self.assertIn(bonus, self._eligible(joiner))
        self.assertNotIn(bonus, self._eligible(outsider))

    def test_moving_department_moves_the_allowance(self):
        bonus = self._allowance(
            "Sales Bonus", "department", apply_departments=[self.sales]
        )
        employee = self._employee("m1@test.horilla", department=self.support)
        self.assertNotIn(bonus, self._eligible(employee))
        info = employee.employee_work_info
        info.department_id = self.sales
        info.save()
        self.assertIn(bonus, self._eligible(employee))

    def test_job_position_and_job_role_allowances(self):
        by_position = self._allowance(
            "Lead Pay", "job_position", apply_job_positions=[self.lead]
        )
        by_role = self._allowance("Closer Pay", "job_role", apply_job_roles=[self.role])
        holder = self._employee("p1@test.horilla", position=self.lead, role=self.role)
        other = self._employee("p2@test.horilla")
        self.assertLessEqual({by_position, by_role}, self._eligible(holder))
        self.assertFalse({by_position, by_role} & self._eligible(other))

    def test_an_excluded_member_is_left_out(self):
        bonus = self._allowance(
            "Sales Bonus", "department", apply_departments=[self.sales]
        )
        member = self._employee("x1@test.horilla", department=self.sales)
        bonus.exclude_employees.add(member)
        self.assertNotIn(bonus, self._eligible(member))

    def test_groups_are_ignored_unless_apply_by_names_them(self):
        picked = self._allowance("Picked", "employees", apply_departments=[self.sales])
        member = self._employee("n1@test.horilla", department=self.sales)
        self.assertNotIn(picked, self._eligible(member))

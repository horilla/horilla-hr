"""
Every way of choosing who gets an allowance, checked on real payslips.

Four employees: two exist before the allowances are made, two join afterwards. Five allowances, one
per option (only selected, all employees, department, job position, job role). Payslips are generated
for all four, so what is asserted is what each person is actually paid.
"""

from datetime import date

from django.test import TestCase

from base.models import Department, JobPosition, JobRole
from employee.models import Employee
from horilla.testkit import make_company, make_employee
from payroll.models.models import Allowance, Contract, Payslip
from payroll.scheduler import generate_payslips

START, END = date(2024, 4, 1), date(2024, 4, 30)
ALL_FIVE = {"Picked", "Everyone", "Dept Sales", "Position Lead", "Role Closer"}


class TargetingFixture(TestCase):
    """Employees and allowances shared by the tests below; it has no tests of its own."""

    def setUp(self):
        self.company = make_company("Targeting Pay Co")
        self.sales = Department.objects.create(department="Pay Sales")
        self.support = Department.objects.create(department="Pay Support")
        self.lead = JobPosition.objects.create(
            job_position="Pay Lead", department_id=self.sales
        )
        self.closer = JobRole.objects.create(
            job_role="Pay Closer", job_position_id=self.lead
        )

        self.old_sales = self._employee(
            "old1@test.horilla", self.sales, self.lead, self.closer
        )
        self.old_support = self._employee("old2@test.horilla", self.support)

        self._allowance("Picked").specific_employees.add(self.old_sales)
        self._allowance("Everyone", include_active_employees=True)
        self._allowance("Dept Sales", apply_by="department").apply_departments.add(
            self.sales
        )
        self._allowance(
            "Position Lead", apply_by="job_position"
        ).apply_job_positions.add(self.lead)
        self._allowance("Role Closer", apply_by="job_role").apply_job_roles.add(
            self.closer
        )

        # Joined after every allowance was set up; nobody added them anywhere.
        self.new_sales = self._employee(
            "new1@test.horilla", self.sales, self.lead, self.closer
        )
        self.new_support = self._employee("new2@test.horilla", self.support)

    def _employee(self, email, department, position=None, role=None):
        employee = make_employee(
            company=self.company, email=email, department=department
        )
        info = employee.employee_work_info
        info.job_position_id = position
        info.job_role_id = role
        info.save()
        Contract.objects.filter(employee_id=employee).delete()
        Contract.objects.create(
            contract_name="Main",
            contract_start_date=START,
            employee_id=employee,
            wage_type="monthly",
            wage=60000.0,
            contract_status="active",
            deduct_leave_from_basic_pay=True,
            calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
        )
        return employee

    def _allowance(self, title, **fields):
        return Allowance.objects.create(
            title=title, is_fixed=True, amount=100.0, is_taxable=True, **fields
        )

    def _paid(self, employee):
        """The allowances on the employee's payslip for the month, as {title: amount}."""
        Payslip.objects.filter(employee_id=employee).delete()
        generate_payslips(Employee.objects.filter(pk=employee.pk), START, END)
        payslip = Payslip.objects.get(employee_id=employee)
        return {
            row["title"]: row["amount"] for row in payslip.pay_head_data["allowances"]
        }


class WhoIsPaidWhatTests(TargetingFixture):
    def test_an_existing_employee_who_is_picked_gets_every_option_that_reaches_them(
        self,
    ):
        paid = self._paid(self.old_sales)
        self.assertEqual(set(paid), ALL_FIVE)
        self.assertTrue(all(round(amount, 2) == 100.0 for amount in paid.values()))

    def test_an_existing_employee_outside_every_group_gets_only_all_employees(self):
        self.assertEqual(set(self._paid(self.old_support)), {"Everyone"})

    def test_a_new_joiner_in_the_groups_is_paid_without_being_added(self):
        # Everything but the hand-picked list: nobody added them to it.
        self.assertEqual(set(self._paid(self.new_sales)), ALL_FIVE - {"Picked"})

    def test_a_new_joiner_outside_the_groups_gets_only_all_employees(self):
        self.assertEqual(set(self._paid(self.new_support)), {"Everyone"})

    def test_adding_a_new_joiner_to_only_selected_pays_them(self):
        Allowance.objects.get(title="Picked").specific_employees.add(self.new_sales)
        self.assertIn("Picked", self._paid(self.new_sales))

    def test_moving_an_employee_into_a_group_starts_the_allowance_and_out_stops_it(
        self,
    ):
        self.assertNotIn("Dept Sales", self._paid(self.new_support))
        info = self.new_support.employee_work_info
        info.department_id = self.sales
        info.save()
        self.assertIn("Dept Sales", self._paid(self.new_support))
        info.department_id = self.support
        info.save()
        self.assertNotIn("Dept Sales", self._paid(self.new_support))

    def test_an_excluded_employee_is_left_out_of_all_employees_and_groups(self):
        for title in ("Everyone", "Dept Sales", "Role Closer"):
            Allowance.objects.get(title=title).exclude_employees.add(self.new_sales)
        self.assertEqual(set(self._paid(self.new_sales)), {"Position Lead"})

    def test_a_group_allowance_ignores_its_groups_unless_apply_by_names_them(self):
        stale = Allowance.objects.get(title="Dept Sales")
        stale.apply_by = "employees"
        stale.save()
        self.assertNotIn("Dept Sales", self._paid(self.old_sales))


class TableShowsWhatPayrollPaysTests(TargetingFixture):
    """The applies table lists the same people payroll will pay, in every mode."""

    def _rows(self, **kwargs):
        from payroll.forms.component_layout import applies_page

        rows, _more, _covered = applies_page(Allowance, None, set(), None, "", **kwargs)
        return {row["pk"]: row for row in rows}

    def test_only_selected_ticks_no_one_by_default(self):
        rows = self._rows()
        self.assertTrue(rows)
        self.assertFalse(any(row["checked"] for row in rows.values()))

    def test_all_employees_ticks_everyone_including_new_joiners(self):
        rows = self._rows(everyone=True)
        for employee in (
            self.old_sales,
            self.old_support,
            self.new_sales,
            self.new_support,
        ):
            self.assertTrue(rows[employee.pk]["checked"])

    def test_a_group_lists_only_its_members_ticked_and_named(self):
        for kind, ids, label in (
            ("department", {self.sales.pk}, "Pay Sales"),
            ("job_position", {self.lead.pk}, "Pay Lead"),
            ("job_role", {self.closer.pk}, "Pay Closer"),
        ):
            rows = self._rows(group=(kind, ids))
            self.assertEqual(set(rows), {self.old_sales.pk, self.new_sales.pk}, kind)
            for row in rows.values():
                self.assertTrue(row["checked"], kind)
                self.assertEqual(row["via"], "group", kind)
                self.assertEqual(row["group_label"], label, kind)

    def test_the_rows_endpoint_filters_by_group(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("tableadmin", is_superuser=True)
        make_employee(company=self.company, email="tableadmin@test.horilla", user=user)
        self.client.force_login(user)
        response = self.client.get(
            reverse("component-applies-rows"),
            {"model": "allowance", "by": "department", "group": str(self.support.pk)},
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # Names are identical in the test factory, so tell people apart by department.
        self.assertIn("Pay Support", body)
        self.assertNotIn("Pay Sales", body)


class DeductionTargetingTests(TargetingFixture):
    """Deductions are targeted the same five ways, in both the pre-tax and post-tax passes."""

    def setUp(self):
        super().setUp()
        # The allowances from the fixture are not under test here.
        Allowance.objects.all().delete()
        from payroll.models.models import Deduction

        self.Deduction = Deduction
        for pretax in (True, False):
            tag = "Pre" if pretax else "Post"
            self._deduction(f"{tag} Picked", pretax).specific_employees.add(
                self.old_sales
            )
            self._deduction(f"{tag} Everyone", pretax, include_active_employees=True)
            self._deduction(
                f"{tag} Dept", pretax, apply_by="department"
            ).apply_departments.add(self.sales)
            self._deduction(
                f"{tag} Position", pretax, apply_by="job_position"
            ).apply_job_positions.add(self.lead)
            self._deduction(
                f"{tag} Role", pretax, apply_by="job_role"
            ).apply_job_roles.add(self.closer)

    def _deduction(self, title, pretax, **fields):
        return self.Deduction.objects.create(
            title=title,
            is_fixed=True,
            amount=50.0,
            is_pretax=pretax,
            is_tax=False,
            **fields,
        )

    def _taken(self, employee):
        Payslip.objects.filter(employee_id=employee).delete()
        generate_payslips(Employee.objects.filter(pk=employee.pk), START, END)
        data = Payslip.objects.get(employee_id=employee).pay_head_data
        rows = data.get("pretax_deductions", []) + data.get("post_tax_deductions", [])
        return {row["title"] for row in rows}

    def _all(self, *names):
        return {f"{tag} {name}" for tag in ("Pre", "Post") for name in names}

    def test_existing_employee_in_the_groups_has_every_option_applied(self):
        self.assertEqual(
            self._taken(self.old_sales),
            self._all("Picked", "Everyone", "Dept", "Position", "Role"),
        )

    def test_existing_employee_outside_the_groups_has_only_all_employees(self):
        self.assertEqual(self._taken(self.old_support), self._all("Everyone"))

    def test_new_joiners_are_covered_without_being_added(self):
        self.assertEqual(
            self._taken(self.new_sales),
            self._all("Everyone", "Dept", "Position", "Role"),
        )
        self.assertEqual(self._taken(self.new_support), self._all("Everyone"))

    def test_an_excluded_employee_is_left_out(self):
        for deduction in self.Deduction.objects.filter(title__endswith="Dept"):
            deduction.exclude_employees.add(self.new_sales)
        self.assertEqual(
            self._taken(self.new_sales), self._all("Everyone", "Position", "Role")
        )

    def test_moving_department_moves_the_deduction(self):
        self.assertNotIn("Pre Dept", self._taken(self.new_support))
        info = self.new_support.employee_work_info
        info.department_id = self.sales
        info.save()
        self.assertIn("Pre Dept", self._taken(self.new_support))

    def test_the_form_saves_a_department_deduction_and_the_table_lists_its_members(
        self,
    ):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("deductionadmin", is_superuser=True)
        make_employee(
            company=self.company, email="deductionadmin@test.horilla", user=user
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("create-deduction"),
            {
                "title": "Form Dept Deduction",
                "sequence": 300,
                "is_pretax": "on",
                "is_fixed": "on",
                "amount": "40",
                "maximum_unit": "month_calendar_days",
                "if_choice": "basic_pay",
                "if_condition": "gt",
                "if_amount": "0",
                "apply_by": "department",
                "apply_departments": [self.support.pk],
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertIn(response.status_code, (200, 302))
        saved = self.Deduction.objects.get(title="Form Dept Deduction")
        self.assertEqual(saved.apply_by, "department")
        self.assertEqual(list(saved.apply_departments.all()), [self.support])
        self.assertFalse(saved.include_active_employees)

        rows = self.client.get(
            reverse("component-applies-rows"),
            {"model": "deduction", "by": "department", "group": str(self.support.pk)},
        )
        body = rows.content.decode()
        self.assertIn("Pay Support", body)
        self.assertNotIn("Pay Sales", body)

    def test_only_selected_with_nobody_chosen_applies_to_nobody(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("emptyadmin", is_superuser=True)
        make_employee(company=self.company, email="emptyadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.client.post(
            reverse("create-deduction"),
            {
                "title": "Nobody Deduction",
                "sequence": 300,
                "is_pretax": "on",
                "is_fixed": "on",
                "amount": "40",
                "maximum_unit": "month_calendar_days",
                "if_choice": "basic_pay",
                "if_condition": "gt",
                "if_amount": "0",
                "apply_by": "employees",
            },
            HTTP_HX_REQUEST="true",
        )
        saved = self.Deduction.objects.get(title="Nobody Deduction")
        self.assertFalse(saved.include_active_employees)
        self.assertNotIn("Nobody Deduction", self._taken(self.old_sales))


class ReadOnlyListsShowGroupsTests(TargetingFixture):
    """The employee-facing lists name a department, job position or job role allowance too."""

    def setUp(self):
        super().setUp()
        Allowance.objects.all().delete()
        self.dept = Allowance.objects.create(
            title="Listed Dept Pay", is_fixed=True, amount=10.0, apply_by="department"
        )
        self.dept.apply_departments.add(self.sales)

    def test_the_structure_employees_rows_say_why_a_group_allowance_reaches_them(self):
        from payroll.models.models import Contract

        contract = Contract.objects.get(employee_id=self.old_sales)
        row = next(
            r for r in contract.component_rows if r["title"] == "Listed Dept Pay"
        )
        self.assertEqual(row["source"], "group")

    def test_the_employee_tab_lists_it_for_members_only(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("listadmin", is_superuser=True)
        make_employee(company=self.company, email="listadmin@test.horilla", user=user)
        self.client.force_login(user)
        hx = {"HTTP_HX_REQUEST": "true"}
        member = self.client.get(
            reverse("allowance-tab-list", kwargs={"pk": self.old_sales.pk}), **hx
        )
        outsider = self.client.get(
            reverse("allowance-tab-list", kwargs={"pk": self.old_support.pk}), **hx
        )
        self.assertIn("Listed Dept Pay", member.content.decode())
        self.assertNotIn("Listed Dept Pay", outsider.content.decode())

    def test_the_allocations_tab_lists_it_for_members_only(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("allocadmin", is_superuser=True)
        make_employee(company=self.company, email="allocadmin@test.horilla", user=user)
        self.client.force_login(user)
        url = reverse("allocation-allowance-list")
        hx = {"HTTP_HX_REQUEST": "true"}
        member = self.client.get(url, {"instance_id": self.old_sales.pk}, **hx)
        outsider = self.client.get(url, {"instance_id": self.old_support.pk}, **hx)
        self.assertIn("Listed Dept Pay", member.content.decode())
        self.assertNotIn("Listed Dept Pay", outsider.content.decode())

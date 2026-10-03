"""
Components, seen and managed from the contract.

A component reaches an employee through ``specific_employees``; a salary
structure is only what puts them there. That has always been the model, and
the contract had no view of it — so which components would actually pay an
employee was only discoverable by opening every component in turn.

The tests that matter are the ones about the FOUR routes a component can take
to an employee. They look identical on a payslip and are completely different
when you want to stop one, and only two of them are a contract's to change.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import make_active_contract


class ComponentRouteTests(TestCase):
    def setUp(self):
        self.company = make_company("Route Co")
        self.employee = make_employee(company=self.company, email="route@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee)

    def _rows(self):
        return {row["title"]: row for row in self.contract.component_rows}

    def test_a_component_targeted_directly_shows_and_can_be_switched_off(self):
        component = Allowance.objects.create(title="Direct", is_fixed=True, amount=100)
        component.specific_employees.add(self.employee)

        row = self._rows()["Direct"]
        self.assertEqual(row["source"], "targeted")
        self.assertTrue(row["can_toggle"])

    def test_a_structure_component_says_so(self):
        structure = SalaryStructure.objects.create(title="Std")
        component = Allowance.objects.create(
            title="Structured", is_fixed=True, amount=100
        )
        structure.allowances.add(component)
        component.specific_employees.add(self.employee)
        self.contract.salary_structure_id = structure
        self.contract.save()

        row = self._rows()["Structured"]
        self.assertEqual(row["source"], "structure")
        self.assertTrue(row["can_toggle"])

    def test_an_everyone_component_shows_but_cannot_be_switched_off_here(self):
        """
        It is not this contract's decision. Turning it off for one person
        means an exclusion on the component, which is a different thing.
        """
        Allowance.objects.create(
            title="Everyone",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )
        row = self._rows()["Everyone"]
        self.assertEqual(row["source"], "everyone")
        self.assertFalse(row["can_toggle"])

    def test_a_condition_based_component_shows_but_cannot_be_switched_off(self):
        Allowance.objects.create(
            title="Conditional",
            is_fixed=True,
            amount=100,
            is_condition_based=True,
            field="children",
            condition="equal",
            value="2",
        )
        row = self._rows()["Conditional"]
        self.assertEqual(row["source"], "conditional")
        self.assertFalse(row["can_toggle"])

    def test_an_excluded_employee_does_not_see_an_everyone_component(self):
        component = Allowance.objects.create(
            title="Not For You",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )
        component.exclude_employees.add(self.employee)
        self.assertNotIn("Not For You", self._rows())

    def test_a_system_template_appears_but_only_as_a_standard_row(self):
        """
        They are listed — the question this answers is "what can reach this
        payslip" — but never as membership: nobody is opted in to loss of pay.
        That they are never actually PAID is asserted in
        test_system_components.NotPayableTests.
        """
        templates = [
            row for row in self.contract.component_rows if row["component"].is_system
        ]
        self.assertTrue(templates)
        for row in templates:
            with self.subTest(title=row["title"]):
                self.assertTrue(row["standard"])
                self.assertFalse(row["can_toggle"])

    def test_a_generated_row_is_marked_and_sorted_last(self):
        """
        A loan instalment is real pay for this employee but not something to
        tick on or off, and a dozen of them would otherwise bury the rest.
        """
        generated = Deduction.objects.create(
            title="Loan - 2026-05-01",
            is_fixed=True,
            amount=500,
            only_show_under_employee=True,
        )
        generated.specific_employees.add(self.employee)
        Allowance.objects.create(
            title="Ordinary",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )

        rows = [r for r in self.contract.component_rows if not r.get("standard")]
        self.assertTrue(rows[-1]["generated"])
        self.assertEqual(rows[-1]["title"], "Loan - 2026-05-01")


class MembershipEditingTests(TestCase):
    def setUp(self):
        user = make_user("compadmin", is_superuser=True)
        self.company = make_company("Comp Co")
        make_employee(company=self.company, email="compadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.employee = make_employee(company=self.company, email="member@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee)
        self.component = Allowance.objects.create(
            title="Toggle Me", is_fixed=True, amount=100
        )

    def _post(self, *tokens):
        return self.client.post(
            reverse("contract-components", kwargs={"pk": self.contract.pk}),
            {"components": list(tokens)},
            **self.hx,
        )

    def test_ticking_adds_the_employee_to_the_component(self):
        self._post(f"allowance:{self.component.pk}")
        self.assertIn(self.employee, self.component.specific_employees.all())

    def test_unticking_removes_them(self):
        self.component.specific_employees.add(self.employee)
        self._post()
        self.assertNotIn(self.employee, self.component.specific_employees.all())

    def test_it_does_not_touch_anyone_else(self):
        """
        The component is shared. Editing membership from one contract must
        leave every other employee on it exactly as they were.
        """
        other = make_employee(company=self.company, email="other@test.horilla")
        self.component.specific_employees.add(other)

        self._post(f"allowance:{self.component.pk}")

        self.assertIn(other, self.component.specific_employees.all())
        self.assertIn(self.employee, self.component.specific_employees.all())

    def test_an_everyone_component_cannot_be_removed_through_this(self):
        """
        The tick is disabled on the form, so a value for it can only be stale
        or forged. Either way it must not take effect.
        """
        everyone = Allowance.objects.create(
            title="Blanket",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )
        self._post()  # nothing ticked at all

        everyone.refresh_from_db()
        self.assertTrue(everyone.include_active_employees)
        self.assertIn("Blanket", {r["title"] for r in self.contract.component_rows})

    def test_the_component_itself_is_never_edited(self):
        before = (self.component.amount, self.component.is_taxable)
        self._post(f"allowance:{self.component.pk}")

        self.component.refresh_from_db()
        self.assertEqual((self.component.amount, self.component.is_taxable), before)


class BulkTests(TestCase):
    def setUp(self):
        user = make_user("bulkadmin", is_superuser=True)
        self.company = make_company("Bulk Co")
        make_employee(company=self.company, email="bulkadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.contracts = []
        for name in ("one", "two", "three"):
            employee = make_employee(company=self.company, email=f"{name}@test.horilla")
            Contract.objects.filter(employee_id=employee).delete()
            self.contracts.append(make_active_contract(employee))

        self.component = Deduction.objects.create(
            title="Union", is_fixed=True, amount=50
        )

    def _ids(self):
        return [str(c.pk) for c in self.contracts]

    def test_adding_a_component_reaches_every_selected_employee(self):
        self.client.post(
            reverse("contracts-bulk-components"),
            {
                "action": "add",
                "instance_ids": self._ids(),
                "components": [f"deduction:{self.component.pk}"],
            },
            **self.hx,
        )
        self.assertEqual(self.component.specific_employees.count(), 3)

    def test_removing_takes_them_all_off(self):
        for contract in self.contracts:
            self.component.specific_employees.add(contract.employee_id)

        self.client.post(
            reverse("contracts-bulk-components"),
            {
                "action": "remove",
                "instance_ids": self._ids(),
                "components": [f"deduction:{self.component.pk}"],
            },
            **self.hx,
        )
        self.assertEqual(self.component.specific_employees.count(), 0)

    def test_assigning_a_structure_puts_them_on_its_components(self):
        """
        Through set_salary_structure, not the field: writing the FK alone
        assigns a structure that then pays nothing.
        """
        structure = SalaryStructure.objects.create(title="Bulk Std")
        earning = Allowance.objects.create(title="Bulk HRA", is_fixed=True, amount=100)
        structure.allowances.add(earning)

        self.client.post(
            reverse("contracts-bulk-components"),
            {
                "action": "structure",
                "instance_ids": self._ids(),
                "salary_structure": structure.pk,
            },
            **self.hx,
        )

        for contract in self.contracts:
            contract.refresh_from_db()
            self.assertEqual(contract.salary_structure_id, structure)
            self.assertIn(contract.employee_id, earning.specific_employees.all())

    def test_nothing_selected_changes_nothing(self):
        self.client.post(
            reverse("contracts-bulk-components"),
            {
                "action": "add",
                "instance_ids": [],
                "components": [f"deduction:{self.component.pk}"],
            },
            **self.hx,
        )
        self.assertEqual(self.component.specific_employees.count(), 0)

    def test_the_form_names_who_it_will_hit(self):
        """
        The selection is made on another screen, which is the easiest kind of
        bulk action to fire at the wrong rows.
        """
        body = self.client.get(
            reverse("contracts-bulk-components"),
            {"instance_ids": self._ids()},
            **self.hx,
        ).content.decode()

        for contract in self.contracts:
            self.assertIn(str(contract.employee_id), body)


class StandardComponentsOnTheContractTests(TestCase):
    """
    The standard pay items shown alongside the chosen ones.

    Loss of pay, loans and fines reach an employee when the thing happens, not
    because anyone ticked them. Leaving them off the contract's list answered
    "what can reach this payslip" wrongly by omission — and that is the
    question the list is opened to answer.
    """

    def setUp(self):
        user = make_user("stdadmin", is_superuser=True)
        self.company = make_company("Std Co")
        make_employee(company=self.company, email="stdadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.employee = make_employee(company=self.company, email="std@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee)

    def test_every_standard_kind_appears_on_the_contract(self):
        from payroll.system_components import SYSTEM_COMPONENTS

        standard = [r for r in self.contract.component_rows if r.get("standard")]
        self.assertEqual(len(standard), len(SYSTEM_COMPONENTS))

    def test_they_are_always_on_and_never_tickable(self):
        for row in self.contract.component_rows:
            if row.get("standard"):
                with self.subTest(title=row["title"]):
                    self.assertFalse(row["can_toggle"])

    def test_they_sort_after_the_chosen_ones(self):
        """Ten always-on rows at the top would bury what is actually chosen."""
        Allowance.objects.create(
            title="Chosen", is_fixed=True, amount=100, include_active_employees=True
        )
        rows = self.contract.component_rows
        first_standard = next(i for i, row in enumerate(rows) if row.get("standard"))
        self.assertTrue(all(not r.get("standard") for r in rows[:first_standard]))

    def test_the_picker_shows_them_ticked_and_disabled(self):
        body = self.client.get(
            reverse("contract-components", kwargs={"pk": self.contract.pk}),
            **self.hx,
        ).content.decode()

        self.assertIn("Loan repayment", body)
        self.assertIn("Standard, always on", body)
        self.assertIn("disabled", body)

    def test_saving_never_targets_one_at_an_employee(self):
        """
        A template is never paid. If a forged post could add an employee to
        one, that employee would get a zero-amount row on every payslip.
        """
        from payroll.models.models import Deduction as D

        template = D.objects.entire().get(system_key="fine")
        self.client.post(
            reverse("contract-components", kwargs={"pk": self.contract.pk}),
            {"components": [f"deduction:{template.pk}"]},
            **self.hx,
        )
        self.assertEqual(template.specific_employees.count(), 0)

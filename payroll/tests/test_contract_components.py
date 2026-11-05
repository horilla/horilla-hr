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

    def test_they_sort_after_the_chosen_ones(self):
        """Ten always-on rows at the top would bury what is actually chosen."""
        Allowance.objects.create(
            title="Chosen", is_fixed=True, amount=100, include_active_employees=True
        )
        rows = self.contract.component_rows
        first_standard = next(i for i, row in enumerate(rows) if row.get("standard"))
        self.assertTrue(all(not r.get("standard") for r in rows[:first_standard]))

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


class ComponentSectionTests(TestCase):
    """The Components tab groups what reaches an employee by how it applies."""

    def setUp(self):
        self.company = make_company("Section Co")
        self.employee = make_employee(
            company=self.company, email="section@test.horilla"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee)

    def _sections(self):
        return {section["key"]: section for section in self.contract.component_sections}

    def _titles(self, key):
        return [row["title"] for row in self._sections()[key]["rows"]]

    def test_each_way_of_applying_has_its_own_section(self):
        structure = SalaryStructure.objects.create(title="Std")
        structured = Allowance.objects.create(
            title="Structured", is_fixed=True, amount=100
        )
        structure.allowances.add(structured)
        structured.specific_employees.add(self.employee)
        self.contract.salary_structure_id = structure
        self.contract.save()
        added = Allowance.objects.create(title="Added", is_fixed=True, amount=100)
        added.specific_employees.add(self.employee)
        Allowance.objects.create(
            title="Everyone", is_fixed=True, amount=100, include_active_employees=True
        )

        self.assertEqual(self._titles("structure"), ["Structured"])
        self.assertEqual(self._titles("outside"), ["Added"])
        self.assertIn("Everyone", self._titles("always"))

    def test_the_sections_are_named_by_how_the_component_applies(self):
        labels = {
            key: str(section["label"]) for key, section in self._sections().items()
        }
        self.assertEqual(labels["always"], "Always Applied")
        added = Allowance.objects.create(title="Added", is_fixed=True, amount=100)
        added.specific_employees.add(self.employee)
        self.assertEqual(
            str(self._sections()["outside"]["label"]), "Outside The Structure"
        )

    def test_the_standard_always_on_items_sit_with_what_applies_to_everyone(self):
        always = self._sections().get("always")
        self.assertIsNotNone(always)
        self.assertTrue(any(row["source"] == "standard" for row in always["rows"]))

    def test_a_condition_based_component_is_outside_the_structure(self):
        Allowance.objects.create(
            title="Conditional",
            is_fixed=True,
            amount=100,
            is_condition_based=True,
            field="employee_work_info__department_id__department",
            condition="equal",
            value="Nowhere",
        )
        self.assertIn("Conditional", self._titles("outside"))

    def test_a_department_component_is_outside_the_structure(self):
        from base.models import Department

        info = self.employee.employee_work_info
        info.department_id = Department.objects.create(department="Section Dept")
        info.save()
        grouped = Allowance.objects.create(
            title="Grouped", is_fixed=True, amount=100, apply_by="department"
        )
        grouped.apply_departments.add(info.department_id)
        self.assertIn("Grouped", self._titles("outside"))

    def test_overtime_for_everyone_is_outside_the_structure_not_always_applied(self):
        for title, based_on in (
            ("Holiday OT", "holiday_overtime"),
            ("Week Off OT", "week_off_overtime"),
            ("Regular OT", "overtime"),
        ):
            Allowance.objects.create(
                title=title,
                is_fixed=False,
                based_on=based_on,
                amount_per_one_hr=10,
                include_active_employees=True,
            )
        Allowance.objects.create(
            title="Everyone", is_fixed=True, amount=100, include_active_employees=True
        )
        self.assertEqual(
            sorted(self._titles("outside")), ["Holiday OT", "Regular OT", "Week Off OT"]
        )
        self.assertNotIn("Holiday OT", self._titles("always"))
        self.assertIn("Everyone", self._titles("always"))

    def test_empty_sections_are_left_out(self):
        self.assertNotIn("outside", self._sections())

    def test_the_sections_are_in_a_fixed_order_and_keep_every_row(self):
        order = [section["key"] for section in self.contract.component_sections]
        wanted = ["structure", "outside", "always", "other"]
        self.assertEqual(order, [key for key in wanted if key in order])
        self.assertEqual(
            sum(len(section["rows"]) for section in self.contract.component_sections),
            len(self.contract.component_rows),
        )

    def test_every_row_is_an_earning_or_a_deduction(self):
        Allowance.objects.create(
            title="Pay", is_fixed=True, amount=100, include_active_employees=True
        )
        Deduction.objects.create(
            title="Pre",
            is_fixed=True,
            amount=10,
            is_pretax=True,
            include_active_employees=True,
        )
        Deduction.objects.create(
            title="Tax",
            is_fixed=True,
            amount=10,
            is_tax=True,
            include_active_employees=True,
        )
        Deduction.objects.create(
            title="Post",
            is_fixed=True,
            amount=10,
            is_pretax=False,
            include_active_employees=True,
        )
        types = {
            row["title"]: str(row["type_label"]) for row in self.contract.component_rows
        }
        self.assertEqual(types["Pay"], "Earning")
        for title in ("Pre", "Tax", "Post"):
            self.assertEqual(types[title], "Deduction", title)

    def _html(self):
        from django.template.loader import render_to_string

        return render_to_string(
            "cbv/contracts/contract_detail.html",
            {
                "instance": self.contract,
                "component_rows": self.contract.component_rows,
                "component_sections": self.contract.component_sections,
                "terms": [],
            },
        )

    def test_the_tab_has_the_new_columns_and_no_how_it_applies_or_manage_block(self):
        Allowance.objects.create(
            title="Everyone",
            code="EVERY",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )
        html = self._html()
        self.assertIn("Always Applied", html)
        self.assertIn('data-cd-section="always"', html)
        self.assertIn("position: sticky", html)
        self.assertIn("table-layout: fixed", html)
        self.assertIn("text-overflow: ellipsis", html)
        self.assertIn(">Type<", html)
        self.assertIn(">Tax<", html)
        self.assertNotIn("How it applies", html)
        self.assertNotIn("Manage components", html)
        self.assertNotIn("A component reaches this employee", html)

    def test_every_row_shows_how_it_is_taxed(self):
        Allowance.objects.create(
            title="Pay",
            is_fixed=True,
            amount=1,
            is_taxable=True,
            include_active_employees=True,
        )
        Allowance.objects.create(
            title="Free",
            is_fixed=True,
            amount=1,
            is_taxable=False,
            include_active_employees=True,
        )
        Deduction.objects.create(
            title="Pre",
            is_fixed=True,
            amount=1,
            is_pretax=True,
            include_active_employees=True,
        )
        Deduction.objects.create(
            title="Post",
            is_fixed=True,
            amount=1,
            is_pretax=False,
            include_active_employees=True,
        )
        Deduction.objects.create(
            title="Tax",
            is_fixed=True,
            amount=1,
            is_tax=True,
            include_active_employees=True,
        )
        tax = {
            row["title"]: str(row["tax_label"]) for row in self.contract.component_rows
        }
        self.assertEqual(
            [tax[t] for t in ("Pay", "Free", "Pre", "Post", "Tax")],
            ["Taxable", "Not Taxable", "Pre-Tax", "Post-Tax", "—"],
        )

    def test_a_standard_item_shows_this_employees_own_tax_setting(self):
        from payroll.models.models import SystemComponentTaxOverride

        SystemComponentTaxOverride.objects.create(
            system_key="loan_payout", employee_id=self.employee, value=False
        )
        rows = {
            row["title"]: str(row["tax_label"])
            for row in self.contract.component_rows
            if row["standard"]
        }
        loan = Allowance.objects.entire().get(system_key="loan_payout")
        self.assertEqual(rows[loan.title], "Not Taxable")
        other = Allowance.objects.entire().get(system_key="advance_payout")
        self.assertEqual(rows[other.title], "Taxable")

    def test_the_code_sits_beside_the_component_name(self):
        Allowance.objects.create(
            title="Everyone",
            code="EVERY",
            is_fixed=True,
            amount=100,
            include_active_employees=True,
        )
        html = self._html()
        self.assertRegex(
            html,
            r'<span class="cd__title"[^>]*>Everyone</span>\s*<span class="cd__code">EVERY</span>',
        )

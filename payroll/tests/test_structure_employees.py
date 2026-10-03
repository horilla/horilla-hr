"""
Who a salary structure can be assigned to.

A structure reaches an employee only through their active contract's
``salary_structure_id``, so assigning one to an employee who already has a
different structure overwrites it — moving them off the other structure with
nothing said, and leaving the other structure's own form showing them missing
with no record of why. And assigning one to an employee with no active
contract does nothing at all, silently.

Both are now refused rather than offered.
"""

from django.http import QueryDict
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.forms.component_forms import SalaryStructureForm
from payroll.methods.structure_rules import assignable_employees, unassignable_reason
from payroll.models.models import Contract, SalaryStructure
from payroll.tests.factories_payroll import make_active_contract


class AssignableEmployeeTests(TestCase):
    def setUp(self):
        self.company = make_company("Assign Co")
        self.structure = SalaryStructure.objects.create(title="Target")
        self.other = SalaryStructure.objects.create(title="Somewhere Else")

    def _employee(self, email, **contract):
        employee = make_employee(company=self.company, email=email)
        Contract.objects.filter(employee_id=employee).delete()
        if contract.pop("active", True):
            make_active_contract(employee, **contract)
        return employee

    def test_an_employee_with_a_free_active_contract_is_offered(self):
        free = self._employee("free@test.horilla")
        self.assertIn(free, assignable_employees(self.structure))
        self.assertIsNone(unassignable_reason(free, self.structure))

    def test_an_employee_with_no_active_contract_is_not_offered(self):
        """There is nothing to write the structure onto."""
        none = self._employee("none@test.horilla", active=False)
        self.assertNotIn(none, assignable_employees(self.structure))
        self.assertEqual(unassignable_reason(none, self.structure), "no_contract")

    def test_an_employee_on_another_structure_is_not_offered(self):
        taken = self._employee("taken@test.horilla", salary_structure_id=self.other)
        self.assertNotIn(taken, assignable_employees(self.structure))
        self.assertEqual(unassignable_reason(taken, self.structure), self.other)

    def test_the_structure_own_employees_stay_offered(self):
        """
        Otherwise editing a structure would offer to remove everyone on it and
        never offer to keep them.
        """
        mine = self._employee("mine@test.horilla", salary_structure_id=self.structure)
        self.assertIn(mine, assignable_employees(self.structure))
        self.assertIsNone(unassignable_reason(mine, self.structure))

    def test_a_draft_contract_does_not_make_someone_assignable(self):
        employee = make_employee(company=self.company, email="draft@test.horilla")
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(employee, contract_status="draft")
        self.assertNotIn(employee, assignable_employees(self.structure))

    def test_an_inactive_assigned_contract_does_not_block_a_free_active_one(self):
        """
        Both conditions have to hold on the SAME contract. An old ended
        contract naming another structure says nothing about today.
        """
        employee = make_employee(company=self.company, email="both@test.horilla")
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(
            employee,
            contract_name="Old",
            contract_status="terminated",
            salary_structure_id=self.other,
        )
        make_active_contract(employee, contract_name="Current")

        self.assertIn(employee, assignable_employees(self.structure))

    def test_nobody_appears_twice(self):
        """
        Filtering across a multi-valued relation can duplicate rows. Contract
        .save() refuses a second ACTIVE contract per employee, so the reachable
        case is an active one alongside an ended one.
        """
        employee = make_employee(company=self.company, email="dupe@test.horilla")
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(
            employee, contract_name="Old", contract_status="terminated"
        )
        make_active_contract(employee, contract_name="Current")

        listed = list(assignable_employees(self.structure))
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(listed.count(employee), 1)


class StructureFormEmployeeTests(TestCase):
    def setUp(self):
        self.company = make_company("Form Co")
        self.structure = SalaryStructure.objects.create(title="Target")
        self.other = SalaryStructure.objects.create(title="Somewhere Else")

    def _employee(self, email, **contract):
        employee = make_employee(company=self.company, email=email)
        Contract.objects.filter(employee_id=employee).delete()
        if contract.pop("active", True):
            make_active_contract(employee, **contract)
        return employee

    def _post(self, *employees):
        """
        A QueryDict, not a dict: SalaryStructureForm.clean() reads the employee
        ids with self.data.getlist(), which a plain dict does not have.
        """
        data = QueryDict(mutable=True)
        data["title"] = "Target"
        data["structure_mode"] = "gross_up"
        data.setlist("employees", [str(one.pk) for one in employees])
        return data

    def test_the_field_offers_only_assignable_employees(self):
        free = self._employee("formfree@test.horilla")
        taken = self._employee("formtaken@test.horilla", salary_structure_id=self.other)
        none = self._employee("formnone@test.horilla", active=False)

        offered = (
            SalaryStructureForm(instance=self.structure).fields["employees"].queryset
        )
        self.assertIn(free, offered)
        self.assertNotIn(taken, offered)
        self.assertNotIn(none, offered)

    def test_submitting_someone_on_another_structure_is_refused(self):
        """
        The widget's filter panel queries through a generic employee route
        that knows nothing of this rule, so the offered list is not the last
        word on what can be submitted.
        """
        taken = self._employee("posttaken@test.horilla", salary_structure_id=self.other)

        form = SalaryStructureForm(data=self._post(taken), instance=self.structure)
        self.assertFalse(form.is_valid())
        message = " ".join(form.errors["employees"])
        self.assertIn("already on another salary structure", message)
        self.assertIn(str(self.other), message)

    def test_submitting_someone_with_no_active_contract_is_refused(self):
        none = self._employee("postnone@test.horilla", active=False)

        form = SalaryStructureForm(data=self._post(none), instance=self.structure)
        self.assertFalse(form.is_valid())
        self.assertIn("no active contract", " ".join(form.errors["employees"]))

    def test_an_assignable_employee_passes(self):
        free = self._employee("postfree@test.horilla")

        form = SalaryStructureForm(data=self._post(free), instance=self.structure)
        self.assertTrue(form.is_valid(), form.errors)


class MissingBasicWarningTests(TestCase):
    """
    A contract the structure cannot work basic pay from.

    Nothing downstream announces this: the payslip still generates, with basic
    zero and every "% of basic pay" on the structure zero with it. So the
    warning has to be raised where the pairing is visible — the structure and
    the contract are each individually fine.
    """

    def setUp(self):
        from horilla.testkit import make_user

        user = make_user("warnadmin", is_superuser=True)
        self.company = make_company("Warn Co")
        make_employee(company=self.company, email="warnadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="Warned")

    def _employee(self, email, **contract):
        employee = make_employee(company=self.company, email=email)
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(employee, salary_structure_id=self.structure, **contract)
        return employee

    def _rows(self):
        return {str(row["employee"]): row for row in self.structure.employee_rows}

    def test_a_zero_wage_with_nothing_else_is_flagged(self):
        self._employee("zero@test.horilla", wage=0)
        self.assertEqual(self.structure.employees_missing_basic, 1)
        self.assertTrue(list(self._rows().values())[0]["no_basic"])

    def test_a_paid_wage_is_not_flagged(self):
        self._employee("paid@test.horilla", wage=30000)
        self.assertEqual(self.structure.employees_missing_basic, 0)
        self.assertFalse(list(self._rows().values())[0]["no_basic"])

    def test_a_flagged_earning_covers_a_zero_wage(self):
        """
        The component works basic out, so the wage never needed to.
        """
        from payroll.models.models import Allowance

        self._employee("covered@test.horilla", wage=0)
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                sequence=10,
                is_basic_pay=True,
                is_fixed=True,
                amount=20000.0,
            )
        )
        self.assertEqual(self.structure.employees_missing_basic, 0)
        self.assertFalse(list(self._rows().values())[0]["no_basic"])

    def test_the_count_matches_the_flagged_rows(self):
        """
        The summary bar counts without resolving the rows, so the two could
        drift apart and tell the user different numbers.
        """
        self._employee("a@test.horilla", wage=0)
        self._employee("b@test.horilla", wage=30000)
        self._employee("c@test.horilla", wage=0)

        flagged = sum(1 for row in self.structure.employee_rows if row["no_basic"])
        self.assertEqual(self.structure.employees_missing_basic, flagged)
        self.assertEqual(flagged, 2)

    def test_ctc_down_dividing_the_wage_has_no_basic_source(self):
        """
        With no CTC of its own the structure divides the wage, so the wage is
        spoken for and nothing is left to read basic from.
        """
        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        self._employee("pot@test.horilla", wage=30000)

        self.assertEqual(self.structure.employees_missing_basic, 1)
        self.assertTrue(list(self._rows().values())[0]["no_basic"])

    def test_the_warning_reaches_the_page(self):
        from django.urls import reverse

        self._employee("shown@test.horilla", wage=0)

        modal = self.client.get(
            reverse("salary-structure-detail-view", kwargs={"pk": self.structure.pk}),
            **self.hx,
        ).content.decode()
        self.assertIn("1 without basic pay", modal)

        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            **self.hx,
        ).content.decode()
        self.assertIn("No basic pay", panel)
        self.assertIn("is-warned", panel)


class EmployeesTabLoadsOnDemandTests(TestCase):
    """
    The one panel whose cost scales with the company: a contract and a
    basic-pay resolution per person, for a tab the modal does not open on.
    """

    def setUp(self):
        from horilla.testkit import make_user

        user = make_user("lazyadmin", is_superuser=True)
        self.company = make_company("Lazy Co")
        self.employee = make_employee(
            company=self.company, email="lazyadmin@test.horilla", user=user
        )
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="Lazy")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, salary_structure_id=self.structure)

    def test_the_modal_does_not_carry_the_rows(self):
        from django.urls import reverse

        body = self.client.get(
            reverse("salary-structure-detail-view", kwargs={"pk": self.structure.pk}),
            **self.hx,
        ).content.decode()

        self.assertIn("data-ssd-lazy", body)
        self.assertIn(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            body,
        )
        # The table itself is not there yet -- only the counts are.
        self.assertNotIn("ss-emp__table", body)
        self.assertIn("1 employee", body)

    def test_the_endpoint_returns_the_rows(self):
        from django.urls import reverse

        response = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("ss-emp__table", body)
        self.assertIn(str(self.employee), body)

    def test_the_endpoint_is_htmx_only(self):
        from django.urls import reverse

        response = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk})
        )
        self.assertNotIn("ss-emp__table", response.content.decode())


class HourlyContractBasicTests(TestCase):
    """
    An hourly contract on a Gross Up structure.

    The engine does work basic pay out for one — compute_salary_on_period
    routes wage_type "hourly" through hourly_computation, and basic_pay is
    `rate / 3600 * regular_seconds`, i.e. the hours actually worked. So the
    contract does state a figure to read basic from; it just cannot be shown
    until attendance exists.

    What it states it in is `hourly_wage`, not `wage`. Checking `wage` called a
    correctly entered hourly contract basic-less and warned about it.
    """

    def setUp(self):
        self.company = make_company("Hourly Co")
        self.structure = SalaryStructure.objects.create(title="Hourly")

    def _hourly(self, email, **contract):
        employee = make_employee(company=self.company, email=email)
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(
            employee,
            salary_structure_id=self.structure,
            wage_type="hourly",
            **contract,
        )
        return employee

    def _row(self):
        return self.structure.employee_rows[0]

    def test_an_hourly_rate_is_a_basic_pay_source(self):
        self._hourly("rate@test.horilla", wage=0, hourly_wage=10.0)

        self.assertEqual(self.structure.employees_missing_basic, 0)
        row = self._row()
        self.assertFalse(row["no_basic"])
        self.assertTrue(row["basic_from_contract"])

    def test_no_figure_is_claimed_for_it(self):
        """
        The period's basic pay is the hours worked times the rate, so a figure
        here would be one payroll never produces.
        """
        self._hourly("figure@test.horilla", wage=0, hourly_wage=10.0)
        self.assertIsNone(self._row()["basic_amount"])

    def test_an_hourly_contract_with_no_rate_is_still_flagged(self):
        self._hourly("norate@test.horilla", wage=0, hourly_wage=0)

        self.assertEqual(self.structure.employees_missing_basic, 1)
        self.assertTrue(self._row()["no_basic"])

    def test_the_count_matches_the_flagged_rows_for_hourly_too(self):
        self._hourly("ok@test.horilla", wage=0, hourly_wage=10.0)
        employee = make_employee(company=self.company, email="bad@test.horilla")
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(
            employee,
            salary_structure_id=self.structure,
            wage_type="hourly",
            wage=0,
            hourly_wage=0,
        )

        flagged = sum(1 for row in self.structure.employee_rows if row["no_basic"])
        self.assertEqual(self.structure.employees_missing_basic, flagged)
        self.assertEqual(flagged, 1)

    def test_the_panel_explains_how_hourly_basic_is_worked_out(self):
        """
        It is the one wage type whose basic pay is not a figure anyone typed
        in, so the table alone cannot say what it is made of.
        """
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("hourlyadmin", is_superuser=True)
        make_employee(company=self.company, email="hourlyadmin@test.horilla", user=user)
        self.client.force_login(user)
        self._hourly("hint@test.horilla", wage=0, hourly_wage=10.0)

        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        self.assertTrue(self.structure.has_hourly_employees)
        self.assertIn("hourly rate", panel)
        self.assertIn("regular hours", panel)
        # And that it wins over an earning marked as basic pay.
        self.assertIn("takes priority", panel)
        self.assertIn("rate × regular hours", panel)

    def test_the_hint_is_absent_when_nobody_is_paid_hourly(self):
        """A note about hourly pay on a wholly monthly structure is noise."""
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("monthlyadmin", is_superuser=True)
        make_employee(
            company=self.company, email="monthlyadmin@test.horilla", user=user
        )
        self.client.force_login(user)

        employee = make_employee(company=self.company, email="monthly@test.horilla")
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(employee, salary_structure_id=self.structure, wage=30000)

        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        self.assertFalse(self.structure.has_hourly_employees)
        # Asserted on the words, not the class: the stylesheet is rendered
        # unconditionally, so the class name is present either way and a check
        # for it would pass whether or not the block was emitted.
        self.assertNotIn("Paid by the hour", panel)
        self.assertNotIn("takes priority", panel)

    def test_the_priority_the_hint_claims_is_the_one_the_engine_applies(self):
        """
        The note says the hours win over an earning marked as basic pay. If
        resolve_basic_pay_source ever stopped agreeing, the note would be
        telling people something untrue about their payslips.
        """
        from payroll.models.models import Allowance

        self._hourly("wins@test.horilla", wage=0, hourly_wage=10.0)
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                sequence=10,
                is_basic_pay=True,
                is_fixed=True,
                amount=20000.0,
            )
        )

        row = self._row()
        self.assertTrue(row["basic_from_contract"])
        self.assertIsNone(row["basic_component"])


class EmployeeSortingTests(TestCase):
    """
    Finding the contracts with no basic pay.

    A name sort buries the one broken contract among fifty working ones, and
    that row is the only reason most people open this tab.
    """

    def setUp(self):
        from horilla.testkit import make_user

        user = make_user("sortadmin", is_superuser=True)
        self.company = make_company("Sort Co")
        make_employee(company=self.company, email="sortadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.structure = SalaryStructure.objects.create(title="Sorted")

    def _employee(self, first_name, wage):
        employee = make_employee(
            company=self.company,
            email=f"{first_name.lower()}@test.horilla",
            first_name=first_name,
        )
        Contract.objects.filter(employee_id=employee).delete()
        make_active_contract(employee, salary_structure_id=self.structure, wage=wage)
        return employee

    def test_the_contracts_with_no_basic_pay_come_first(self):
        """
        Asserted on the order, not merely on presence: alphabetically the
        broken one here sorts last, so a name sort would hide it at the bottom.
        """
        self._employee("Aaron", 30000)
        self._employee("Brenda", 30000)
        self._employee("Zoe", 0)

        names = [str(row["employee"]) for row in self.structure.employee_rows]
        self.assertTrue(names[0].startswith("Zoe"))
        self.assertTrue(self.structure.employee_rows[0]["no_basic"])

    def test_the_rest_stay_alphabetical(self):
        self._employee("Brenda", 30000)
        self._employee("Aaron", 30000)

        names = [str(row["employee"]) for row in self.structure.employee_rows]
        self.assertEqual(names, sorted(names))

    def test_the_order_holds_without_javascript(self):
        """
        The panel offers other orders on its column headings, but the one that
        matters is applied server-side so it survives with JS off.
        """
        from django.urls import reverse

        self._employee("Aaron", 30000)
        self._employee("Zoe", 0)

        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        self.assertLess(panel.index("Zoe"), panel.index("Aaron"))

    def test_the_columns_offer_sorting(self):
        from django.urls import reverse

        self._employee("Aaron", 30000)
        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        for key in ("name", "pay", "other", "basic"):
            self.assertIn(f'data-emp-sort="{key}"', panel)
        # And the Basic pay column starts marked as the one in force, since
        # that is the order the rows arrive in.
        self.assertIn(
            'data-emp-sort="basic"\n                    aria-sort="ascending"', panel
        )

    def test_every_row_carries_what_it_is_sorted_by(self):
        """A row missing a sort key would silently fall to one end."""
        from django.urls import reverse

        self._employee("Aaron", 30000)
        self._employee("Zoe", 0)
        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

        # Counted on the attributes as they are WRITTEN on a row. A bare
        # "data-emp-row" also appears in the panel's own querySelectorAll, so
        # counting that matches the selector as well as the rows.
        self.assertIn("data-emp-row", panel)
        for key in ("data-name=", "data-pay=", "data-other=", "data-basic="):
            self.assertEqual(panel.count(key), 2, key)


class ContractLinkTests(TestCase):
    """
    Getting from a row to the contract behind it.

    The contract opens as an edit form over this modal. contract_update
    already renders a modal-ready fragment for an HTMX request, so this needs
    no page of its own — and a page navigation would have discarded whatever
    was being read in the structure modal.
    """

    def setUp(self):
        from horilla.testkit import make_user

        user = make_user("linkadmin", is_superuser=True)
        self.company = make_company("Link Co")
        make_employee(company=self.company, email="linkadmin@test.horilla", user=user)
        self.client.force_login(user)

        self.structure = SalaryStructure.objects.create(title="Linked")
        self.employee = make_employee(company=self.company, email="linked@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, salary_structure_id=self.structure)

    def _panel(self):
        from django.urls import reverse

        return self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()

    def test_each_row_opens_its_own_contract(self):
        from django.urls import reverse

        contract = Contract.objects.get(employee_id=self.employee)
        self.assertIn(reverse("update-contract", args=[contract.id]), self._panel())

    def test_it_opens_beside_the_structure_rather_than_replacing_it(self):
        """
        Into #relatedObjectModal, not the modal this table is in — that one is
        the salary structure, and replacing it would lose the context the
        contract is being read against.
        """
        panel = self._panel()
        self.assertIn("#relatedObjectModalBody", panel)
        self.assertIn('data-target="#relatedObjectModal"', panel)

    def test_the_form_it_opens_is_one_a_modal_can_hold(self):
        """
        contract_update renders a full page for a plain GET and a fragment for
        an HTMX one. The modal gets the fragment, so this asserts the HTMX
        response is not a whole document.
        """
        from django.urls import reverse

        contract = Contract.objects.get(employee_id=self.employee)
        response = self.client.get(
            reverse("update-contract", args=[contract.id]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<html", response.content.decode().lower())

    def test_saving_refreshes_the_table_it_was_opened_from(self):
        """
        The figures here come from the contract, so a saved wage has to be
        reflected — including whether the row still warns about basic pay.
        """
        panel = self._panel()
        self.assertIn("reloadPayrollContracts", panel)
        self.assertIn("relatedObjectModal", panel)

    def test_someone_who_cannot_change_a_contract_gets_no_edit_link(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        plain = make_user("noedit")
        make_employee(company=self.company, email="noedit@test.horilla", user=plain)
        self.client.force_login(plain)

        contract = Contract.objects.get(employee_id=self.employee)
        panel = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            HTTP_HX_REQUEST="true",
        ).content.decode()
        self.assertNotIn(reverse("update-contract", args=[contract.id]), panel)

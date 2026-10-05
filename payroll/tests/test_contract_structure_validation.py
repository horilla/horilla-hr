"""
A contract has to state what its salary structure needs, and has to say so when
it is saved rather than when the payroll run reaches it.

Gross Up reads the wage as basic pay, so it needs a basic pay from somewhere.
CTC Down divides the Monthly CTC into components, so that figure has to be set.
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.batch_run import BLOCKING, _exceptions_for
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure


class ContractStructureValidationTests(TestCase):
    def setUp(self):
        company = make_company("Validation Co")
        self.employee = make_employee(company=company, email="v@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.gross_up = SalaryStructure.objects.create(
            title="Gross Up Structure", structure_mode="gross_up"
        )
        self.ctc_down = SalaryStructure.objects.create(
            title="CTC Down Structure", structure_mode="ctc_down"
        )

    def _contract(self, structure, **kwargs):
        fields = dict(
            contract_name="Test contract",
            employee_id=self.employee,
            contract_start_date=datetime.date(2024, 1, 1),
            contract_status="draft",
            wage_type="monthly",
            wage=0,
            calculate_daily_leave_amount=True,
            salary_structure_id=structure,
        )
        fields.update(kwargs)
        return Contract(**fields)

    def test_gross_up_without_a_basic_pay_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._contract(self.gross_up, wage=0).clean()
        self.assertIn("wage", caught.exception.message_dict)

    def test_gross_up_with_a_wage_passes(self):
        self._contract(self.gross_up, wage=30000.0).clean()

    def test_gross_up_with_an_earning_flagged_as_basic_pay_passes(self):
        allowance = Allowance.objects.create(
            title="Basic",
            code="BASIC",
            sequence=1,
            is_fixed=True,
            amount=20000,
            is_basic_pay=True,
        )
        self.gross_up.allowances.add(allowance)
        self._contract(self.gross_up, wage=0).clean()

    def test_ctc_down_without_a_monthly_ctc_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._contract(self.ctc_down, wage=50000.0, monthly_ctc=None).clean()
        self.assertIn("monthly_ctc", caught.exception.message_dict)

    def test_ctc_down_with_a_zero_monthly_ctc_is_refused(self):
        with self.assertRaises(ValidationError):
            self._contract(self.ctc_down, monthly_ctc=0).clean()

    def test_ctc_down_with_a_monthly_ctc_passes(self):
        self._contract(self.ctc_down, wage=0, monthly_ctc=80000.0).clean()

    def test_no_structure_asks_for_nothing_extra(self):
        self._contract(None, wage=0).clean()


class ReviewWarningNamesTheWageTypeTests(TestCase):
    """A monthly employee must not be told about an hourly rate."""

    def setUp(self):
        company = make_company("Warning Co")
        self.employee = make_employee(company=company, email="w@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _message(self, wage_type):
        contract = Contract.objects.create(
            contract_name="c",
            employee_id=self.employee,
            contract_start_date=datetime.date(2024, 1, 1),
            contract_status="active",
            wage_type=wage_type,
            wage=0,
            calculate_daily_leave_amount=True,
        )
        problems = _exceptions_for({}, self.employee, contract)
        blocking = [text for severity, text in problems if severity == BLOCKING]
        Contract.objects.filter(pk=contract.pk).delete()
        return blocking[0]

    def test_monthly_contract_says_monthly_wage(self):
        message = self._message("monthly")
        self.assertIn("monthly wage", message)
        self.assertNotIn("hourly", message)

    def test_daily_contract_says_daily_wage(self):
        self.assertIn("daily wage", self._message("daily"))


class StructureMembershipFollowsTheContractTests(TestCase):
    """
    Payslip calculation reads each component's specific_employees, so a contract
    that names a structure has to be added to its components however the
    structure was chosen -- the contract form never went through
    set_salary_structure, and the employee got basic pay and nothing else.
    """

    def setUp(self):
        company = make_company("Membership Co")
        self.employee = make_employee(company=company, email="m@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.hra = Allowance.objects.create(
            title="HRA", code="HRA", sequence=10, is_fixed=True, amount=1000
        )
        self.pf = Deduction.objects.create(
            title="PF", code="PF", sequence=10, is_fixed=True, amount=100
        )
        self.structure = SalaryStructure.objects.create(title="Std")
        self.structure.allowances.add(self.hra)
        self.structure.deductions.add(self.pf)

    def _contract(self, structure=None, status="active"):
        return Contract.objects.create(
            contract_name="c",
            employee_id=self.employee,
            contract_start_date=datetime.date(2024, 1, 1),
            contract_status=status,
            wage_type="monthly",
            wage=20000.0,
            calculate_daily_leave_amount=True,
            salary_structure_id=structure,
        )

    def test_naming_the_structure_on_save_adds_the_employee(self):
        self._contract(self.structure)
        self.assertIn(self.employee, self.hra.specific_employees.all())
        self.assertIn(self.employee, self.pf.specific_employees.all())

    def test_picking_the_structure_later_adds_the_employee(self):
        contract = self._contract(None)
        self.assertNotIn(self.employee, self.hra.specific_employees.all())
        contract.salary_structure_id = self.structure
        contract.save()
        self.assertIn(self.employee, self.hra.specific_employees.all())

    def test_changing_the_structure_moves_the_employee(self):
        other_hra = Allowance.objects.create(
            title="Other", code="OTH", sequence=20, is_fixed=True, amount=500
        )
        other = SalaryStructure.objects.create(title="Other")
        other.allowances.add(other_hra)
        contract = self._contract(self.structure)
        contract.salary_structure_id = other
        contract.save()
        self.assertNotIn(self.employee, self.hra.specific_employees.all())
        self.assertIn(self.employee, other_hra.specific_employees.all())

    def test_resaving_repairs_a_contract_that_was_missed(self):
        contract = self._contract(self.structure)
        self.hra.specific_employees.remove(self.employee)
        contract.save()
        self.assertIn(self.employee, self.hra.specific_employees.all())

    def test_a_draft_contract_does_not_pull_the_employee_in(self):
        self._contract(self.structure, status="draft")
        self.assertNotIn(self.employee, self.hra.specific_employees.all())


class PayFrequencyChoicesTests(TestCase):
    """Weekly and semi-monthly are listed but cannot be picked: the engine pays monthly."""

    def setUp(self):
        from payroll.forms.forms import ContractForm

        self.form_class = ContractForm
        company = make_company("Frequency Co")
        self.employee = make_employee(company=company, email="f@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def test_weekly_and_semi_monthly_are_disabled_but_listed(self):
        html = str(self.form_class()["pay_frequency"])
        self.assertIn("Weekly", html)
        self.assertIn("Semi-Monthly", html)
        for value in ("weekly", "semi_monthly"):
            option = html.split(f'value="{value}"')[1].split(">")[0]
            self.assertIn("disabled", option, value)
        monthly = html.split('value="monthly"')[1].split(">")[0]
        self.assertNotIn("disabled", monthly)

    def test_a_posted_weekly_is_refused(self):
        form = self.form_class()
        form.cleaned_data = {"pay_frequency": "weekly"}
        with self.assertRaises(ValidationError):
            form.clean_pay_frequency()

    def test_monthly_is_accepted(self):
        form = self.form_class()
        form.cleaned_data = {"pay_frequency": "monthly"}
        self.assertEqual(form.clean_pay_frequency(), "monthly")

    def test_a_contract_already_on_weekly_can_still_be_edited(self):
        contract = Contract.objects.create(
            contract_name="c",
            employee_id=self.employee,
            contract_start_date=datetime.date(2024, 1, 1),
            contract_status="draft",
            wage_type="monthly",
            wage=100.0,
            pay_frequency="weekly",
            calculate_daily_leave_amount=True,
        )
        form = self.form_class(instance=contract)
        html = str(form["pay_frequency"])
        weekly = html.split('value="weekly"')[1].split(">")[0]
        self.assertNotIn("disabled", weekly)
        form.cleaned_data = {"pay_frequency": "weekly"}
        self.assertEqual(form.clean_pay_frequency(), "weekly")

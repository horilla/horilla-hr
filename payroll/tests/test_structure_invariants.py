"""
Where basic pay comes from, and structures that cannot say.

Basic pay can be stated in two places and both are legitimate: the contract
wage, or an earning on the salary structure marked is_basic_pay. The rule is
that the contract wins and the earning is the fallback, which is not guessable
from either screen — so it is enforced in one place and explained on the
structure.

The consequence that has to hold is what happens to the flagged earning when
the contract does state a wage: it must be skipped, not paid. Paying it would
put a second basic into gross. That is the reason the precedence lives in its
own module rather than being an "or" somewhere in the engine.

A CTC Down structure is the case the numbers alone cannot settle: there the
wage is the package being divided, so it says nothing about basic and the
earning is the only source. Without one basic pay would be nothing, and a
filing status based on basic pay would tax nothing, so the run is refused
rather than producing a payslip that looks complete.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import StructureConfigurationError, payroll_calculation
from payroll.methods.structure_rules import structure_problems
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

WORKING_DAYS = 22
PER_DAY = 1000.0
# A whole period pays the whole monthly wage.
MONTHLY_WAGE = 30000.0
EMPTY_LEAVES = {
    "paid_leave": 0,
    "unpaid_leaves": 0,
    "partial_pay_days": 0,
    "total_leaves": 0,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}


class Stub:
    """A component-shaped object, for the rules' own behaviour."""

    def __init__(
        self,
        is_basic_pay=False,
        based_on=None,
        sequence=100,
        is_fixed=False,
        title="Stub",
    ):
        self.is_basic_pay = is_basic_pay
        self.based_on = based_on
        self.sequence = sequence
        self.is_fixed = is_fixed
        self.title = title


class StructureRuleTests(SimpleTestCase):
    def test_ctc_down_without_a_basic_earning_is_a_problem(self):
        problems = structure_problems("ctc_down", [Stub()])
        self.assertEqual(len(problems), 1)
        self.assertIn("basic pay", str(problems[0]))

    def test_ctc_down_with_one_basic_earning_is_fine(self):
        self.assertEqual(structure_problems("ctc_down", [Stub(is_basic_pay=True)]), [])

    def test_two_basic_earnings_is_a_problem_in_either_mode(self):
        for mode in ("ctc_down", "gross_up"):
            with self.subTest(mode=mode):
                problems = structure_problems(
                    mode,
                    [
                        Stub(is_basic_pay=True, title="A"),
                        Stub(is_basic_pay=True, title="B"),
                    ],
                )
                self.assertTrue(any("Only one earning" in str(p) for p in problems))

    def test_gross_up_with_a_basic_earning_is_allowed(self):
        """
        It is the fallback for an employee whose contract has no wage, so it is
        a legitimate thing to have — unlike under the previous code-matching
        rule, which had to forbid it to avoid double-counting. The precedence
        does that job now.
        """
        self.assertEqual(structure_problems("gross_up", [Stub(is_basic_pay=True)]), [])

    def test_a_balance_component_only_belongs_in_ctc_down(self):
        problems = structure_problems("gross_up", [Stub(based_on="balance")])
        self.assertTrue(any("CTC Down" in str(p) for p in problems))

    def test_a_balance_component_has_to_run_last(self):
        problems = structure_problems(
            "ctc_down",
            [
                Stub(is_basic_pay=True, sequence=10),
                Stub(based_on="balance", sequence=20, title="Special"),
                Stub(sequence=30, title="Other"),
            ],
        )
        self.assertTrue(any("last" in str(p) for p in problems))

    def test_a_balance_component_with_the_highest_sequence_is_fine(self):
        self.assertEqual(
            structure_problems(
                "ctc_down",
                [
                    Stub(is_basic_pay=True, sequence=10),
                    Stub(based_on="balance", sequence=900),
                ],
            ),
            [],
        )

    def test_a_missing_mode_reads_as_gross_up(self):
        """Every structure predating the mode field has it empty."""
        self.assertEqual(structure_problems(None, [Stub()]), [])
        self.assertEqual(structure_problems(None, [Stub(is_basic_pay=True)]), [])


class BasicPayPrecedenceTests(TestCase):
    """
    The contract wins; the flagged earning is the fallback. Both halves, and
    the skip that stops basic being counted twice.
    """

    def setUp(self):
        company = make_company("Precedence Co")
        self.employee = make_employee(company=company, email="prec@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _run(self):
        def months(wage, *_args, **_kwargs):
            # Derived from the wage it is handed, not a constant: monthly_computation
            # builds basic pay out of per_day_amount, so a constant would produce
            # 22,000 of basic for a contract with no wage at all.
            return [
                {
                    "working_days_on_period": WORKING_DAYS,
                    "working_days_on_month": WORKING_DAYS,
                    "days": 30,
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                    "per_day_amount": (float(wage or 0)) / WORKING_DAYS,
                }
            ]

        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": PER_DAY},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            return payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

    def _flagged(self, amount=5000.0):
        allowance = Allowance.objects.create(
            title="Basic Pay",
            sequence=10,
            is_basic_pay=True,
            is_fixed=True,
            amount=amount,
            is_taxable=True,
            maximum_unit="full_period",
        )
        allowance.specific_employees.add(self.employee)
        return allowance

    def test_the_contract_wage_is_basic_pay_when_it_is_stated(self):
        make_active_contract(self.employee, wage=30000.0)
        self.assertAlmostEqual(self._run()["basic_pay"], MONTHLY_WAGE, places=2)

    def test_the_flagged_earning_is_not_paid_when_the_contract_states_basic(self):
        """
        The whole reason the precedence is explicit. Paying it as well would add
        a second basic on top of the one already in gross.
        """
        make_active_contract(self.employee, wage=30000.0)
        self._flagged()

        data = self._run()
        titles = [line["title"] for line in data["allowances"]]
        self.assertNotIn("Basic Pay", titles)
        self.assertAlmostEqual(data["basic_pay"], MONTHLY_WAGE, places=2)
        self.assertAlmostEqual(data["gross_pay"], MONTHLY_WAGE, places=2)

    def test_the_flagged_earning_is_used_when_the_contract_has_no_wage(self):
        make_active_contract(self.employee, wage=0.0)
        self._flagged(amount=7000.0)

        data = self._run()
        self.assertEqual(data["basic_pay"], 7000.0)
        self.assertEqual(data["gross_pay"], 7000.0)

    def test_no_wage_and_no_flagged_earning_is_refused(self):
        """
        Previously this produced a payslip with no basic pay at all, which a
        filing status based on basic pay would then tax at nothing.
        """
        make_active_contract(self.employee, wage=0.0)
        with self.assertRaises(StructureConfigurationError):
            self._run()


class CtcDownGuardTests(TestCase):
    def setUp(self):
        company = make_company("Guard Co")
        self.employee = make_employee(company=company, email="guard@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.structure = SalaryStructure.objects.create(
            title="Broken CTC", structure_mode="ctc_down"
        )
        make_active_contract(
            self.employee, wage=60000.0, salary_structure_id=self.structure
        )

    def _run(self):
        with patch(
            "payroll.methods.methods.months_between_range",
            return_value=[
                {"working_days_on_period": WORKING_DAYS, "per_day_amount": PER_DAY}
            ],
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": PER_DAY},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            return payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

    def test_ctc_down_with_no_basic_component_shows_zero_basic(self):
        """
        Under CTC Down basic is the flagged earning and nothing else. With none
        flagged it is zero -- the contract wage is not read as basic -- and the
        payslip still runs.
        """
        other = Allowance.objects.create(
            title="Allowance",
            sequence=10,
            is_fixed=True,
            amount=1000.0,
            is_taxable=True,
            maximum_unit="full_period",
        )
        other.specific_employees.add(self.employee)

        data = self._run()
        self.assertEqual(data["basic_pay"], 0)

    def test_ctc_down_with_a_basic_component_runs(self):
        basic = Allowance.objects.create(
            title="Basic Pay",
            sequence=10,
            is_basic_pay=True,
            is_fixed=False,
            based_on="component",
            percentage_of_code="CTC",
            rate=50.0,
            is_taxable=True,
        )
        basic.specific_employees.add(self.employee)
        self.assertGreater(self._run()["basic_pay"], 0)


class StructureFormValidationTests(TestCase):
    """The form is what stops a bad set being stored in the first place."""

    def _form(self, mode, allowances=(), deductions=()):
        """
        Built on a QueryDict: the form's clean() reads the employee list with
        .getlist(), which a plain dict does not have.
        """
        from django.http import QueryDict

        from payroll.forms.component_forms import SalaryStructureForm

        data = QueryDict(mutable=True)
        data["title"] = "Test"
        data["structure_mode"] = mode
        data.setlist("allowances", [str(a.pk) for a in allowances])
        data.setlist("deductions", [str(d.pk) for d in deductions])
        return SalaryStructureForm(data)

    def test_two_basic_earnings_are_refused(self):
        form = self._form(
            "gross_up",
            [
                Allowance.objects.create(
                    title="A", is_basic_pay=True, is_fixed=True, amount=1
                ),
                Allowance.objects.create(
                    title="B", is_basic_pay=True, is_fixed=True, amount=1
                ),
            ],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("allowances", form.errors)

    def test_ctc_down_without_a_basic_earning_is_refused(self):
        hra = Allowance.objects.create(title="HRA", is_fixed=True, amount=1)
        form = self._form("ctc_down", [hra])
        self.assertFalse(form.is_valid())
        self.assertIn("allowances", form.errors)

    def test_a_coherent_structure_validates(self):
        hra = Allowance.objects.create(title="HRA", is_fixed=True, amount=1)
        self.assertTrue(self._form("gross_up", [hra]).is_valid())

    def test_the_mode_is_on_the_form_at_all(self):
        """
        It was not. The engine read structure_mode and the model documented it,
        but the form's field list omitted it — so CTC Down could not be chosen
        anywhere outside a shell.
        """
        from payroll.forms.component_forms import SalaryStructureForm

        self.assertIn("structure_mode", SalaryStructureForm().fields)

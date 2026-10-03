"""
CTC Down structures.

Gross Up — the contract wage IS basic pay, and allowances stack on top — was
the only model legacy payroll had. An employer who states a total cost and
divides it into components had no way to express that, and no way to make the
parts sum exactly to the whole.

An employee with no salary structure, or one left on Gross Up, follows exactly
the path they always did; that is what the golden suite guards.
"""

from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

WORKING_DAYS = 22
PER_DAY = 1000.0
# CTC is prorated for the period exactly as basic pay is, so it is the
# period figure the components divide — not the annual/contract wage.
PERIOD_CTC = WORKING_DAYS * PER_DAY  # 22,000
EXPECTED_BASIC = PERIOD_CTC * 0.50  # 11,000
EXPECTED_HRA = EXPECTED_BASIC * 0.40  #  4,400
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


class CtcDownSetup:
    """Shared fixture. Not a TestCase, so the cases below do not
    inherit — and re-run — each other's tests."""

    def setUp(self):
        company = make_company("CTC Co")
        self.employee = make_employee(company=company, email="ctc@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.structure = SalaryStructure.objects.create(
            title="CTC Structure", structure_mode="ctc_down"
        )
        self.contract = make_active_contract(
            self.employee, wage=60000.0, salary_structure_id=self.structure
        )

    def _allowance(self, title, code, sequence, **kw):
        allowance = Allowance.objects.create(
            title=title, code=code, sequence=sequence, is_taxable=True, **kw
        )
        allowance.specific_employees.add(self.employee)
        return allowance

    def _standard_structure(self):
        """Basic = 50% of CTC, HRA = 40% of basic, the rest absorbed."""
        self._allowance(
            "Basic Pay",
            "BASIC",
            10,
            is_fixed=False,
            is_basic_pay=True,
            based_on="component",
            percentage_of_code="CTC",
            rate=50.0,
        )
        self._allowance(
            "HRA",
            "HRA",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
        )
        self._allowance(
            "Special Allowance", "SPECIAL", 900, is_fixed=False, based_on="balance"
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

    def _named(self, lines, title):
        return next(line["amount"] for line in lines if line["title"] == title)


class CtcDownTests(CtcDownSetup, TestCase):
    def test_components_sum_exactly_to_ctc(self):
        """
        The whole point of a balance component: the parts add up to the stated
        total, not to whatever the percentages happen to come to.
        """
        self._standard_structure()
        data = self._run()
        # Basic pay is stored as the payslip's own figure, not as one of the
        # rows beside it -- the same shape a Gross Up payslip has, so that
        # "basic plus the allowances" is the whole of gross in either mode.
        total = data["basic_pay"] + sum(line["amount"] for line in data["allowances"])
        self.assertAlmostEqual(total, PERIOD_CTC, places=2)

    def test_basic_pay_is_stored_once_not_twice(self):
        """
        It used to be in both places at once: the payslip's basic_pay and its
        own row among the allowances. Every reader that showed the rows beside
        basic pay showed the same money twice, and the payslip editor added it
        to gross a second time.
        """
        self._standard_structure()
        data = self._run()
        titles = [line["title"] for line in data["allowances"]]
        self.assertNotIn("Basic Pay", titles)
        self.assertAlmostEqual(data["basic_pay"], EXPECTED_BASIC, places=2)

    def test_wage_is_treated_as_ctc_not_basic(self):
        self._standard_structure()
        data = self._run()
        self.assertAlmostEqual(data["contract_wage"], 60000.0, places=2)
        self.assertAlmostEqual(data["basic_pay"], EXPECTED_BASIC, places=2)
        self.assertAlmostEqual(
            self._named(data["allowances"], "HRA"), EXPECTED_HRA, places=2
        )

    def test_gross_does_not_double_count_basic(self):
        """
        Basic IS one of the allowances here, so the usual
        gross = basic + allowances would count it twice.
        """
        self._standard_structure()
        data = self._run()
        self.assertAlmostEqual(data["gross_pay"], PERIOD_CTC, places=2)

    def test_balance_absorbs_the_remainder(self):
        self._standard_structure()
        data = self._run()
        named = EXPECTED_BASIC + EXPECTED_HRA
        self.assertAlmostEqual(
            self._named(data["allowances"], "Special Allowance"),
            PERIOD_CTC - named,
            places=2,
        )

    def test_balance_never_goes_negative(self):
        """If the named components already exceed CTC, the balance is 0 — it
        does not pay the difference back."""
        self._allowance(
            "Basic Pay", "BASIC", 10, is_fixed=True, amount=50000.0, is_basic_pay=True
        )
        self._allowance("Huge", "HUGE", 20, is_fixed=True, amount=40000.0)
        self._allowance("Balance", "BAL", 900, is_fixed=False, based_on="balance")
        data = self._run()
        self.assertEqual(self._named(data["allowances"], "Balance"), 0)

    def test_deductions_see_the_derived_basic(self):
        """PF is a percentage of basic — which in this mode is computed, not given."""
        self._standard_structure()
        pf = Deduction.objects.create(
            title="PF",
            code="PF",
            sequence=950,
            is_pretax=True,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=12.0,
        )
        pf.specific_employees.add(self.employee)
        data = self._run()
        self.assertAlmostEqual(
            self._named(data["pretax_deductions"], "PF"),
            EXPECTED_BASIC * 0.12,
            places=2,
        )

    def test_components_are_not_gated_off_by_a_zero_starting_basic(self):
        """
        Every component carries a hidden "basic pay > 0" gate. Basic is derived
        from the components here, so it is 0 while they run — which zeroed every
        one of them until the gate learned to fall back to CTC.
        """
        self._standard_structure()
        data = self._run()
        # Basic pay is not among the rows any more, so it is checked on its
        # own -- it is the component the gate hit hardest, being the one every
        # other percentage is taken of.
        self.assertGreater(data["basic_pay"], 0, "Basic Pay was gated off")
        for line in data["allowances"]:
            self.assertGreater(line["amount"], 0, f"{line['title']} was gated off")

    def test_gross_up_structure_is_unaffected(self):
        """A structure left on the default mode behaves exactly as before."""
        self.structure.structure_mode = "gross_up"
        self.structure.save()
        self._allowance("Flat", "FLAT", 20, is_fixed=True, amount=5000.0)
        data = self._run()
        # wage is basic pay again, and the allowance stacks on top of it
        self.assertAlmostEqual(data["basic_pay"], 22000.0, places=2)
        self.assertAlmostEqual(data["gross_pay"], 27000.0, places=2)

    def test_employee_without_a_structure_is_unaffected(self):
        self.contract.salary_structure_id = None
        self.contract.save()
        self._allowance("Flat", "FLAT", 20, is_fixed=True, amount=5000.0)
        data = self._run()
        self.assertAlmostEqual(data["basic_pay"], 22000.0, places=2)
        self.assertAlmostEqual(data["gross_pay"], 27000.0, places=2)


class GrossDerivedComponentTests(CtcDownSetup, TestCase):
    """
    Defining a component as a percentage of GROSS.

    "Basic is 50% of gross" is how a great many structures are actually
    written, and it is inexpressible in a Gross Up run for a reason that is not
    a shortcoming: there, gross is only discovered by adding basic to
    everything stacked on top of it, so a basic derived from gross would be
    defined in terms of itself.

    A CTC Down structure knows the total before anything runs, so gross is
    available to the first component. These pin that down, and pin down that it
    does not drift as the pass proceeds.
    """

    def test_basic_can_be_stated_as_a_percentage_of_gross(self):
        self._allowance(
            "Basic Pay",
            "BASIC",
            10,
            is_fixed=False,
            is_basic_pay=True,
            based_on="component",
            percentage_of_code="GROSS",
            rate=50.0,
        )
        self._allowance(
            "Special Allowance", "SPECIAL", 900, is_fixed=False, based_on="balance"
        )
        data = self._run()

        self.assertAlmostEqual(data["basic_pay"], EXPECTED_BASIC, places=2)
        self.assertAlmostEqual(data["gross_pay"], PERIOD_CTC, places=2)

    def test_gross_and_ctc_name_the_same_figure_here(self):
        """
        Both readings of the wage have to agree, or the same structure would
        pay differently depending on which name the admin happened to pick.
        """
        for code in ("GROSS", "CTC"):
            with self.subTest(percentage_of=code):
                Allowance.objects.all().delete()
                self._allowance(
                    "Basic Pay",
                    "BASIC",
                    10,
                    is_fixed=False,
                    is_basic_pay=True,
                    based_on="component",
                    percentage_of_code=code,
                    rate=50.0,
                )
                self.assertAlmostEqual(
                    self._run()["basic_pay"], EXPECTED_BASIC, places=2
                )

    def test_gross_does_not_grow_as_the_components_run(self):
        """
        Gross is the pot being divided, so it is already final. While it was
        also the running earnings total, a component late in the order saw a
        larger gross than an identical one early in it — so two components
        configured the same way paid different amounts.
        """
        # The first is the basic pay earning: a CTC Down structure has to have
        # one, and what this test is about — GROSS not moving as the pass runs —
        # is unaffected by which component carries the flag.
        self._allowance(
            "First",
            "FIRST",
            10,
            is_fixed=False,
            is_basic_pay=True,
            based_on="component",
            percentage_of_code="GROSS",
            rate=10.0,
        )
        self._allowance(
            "Second",
            "SECOND",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="GROSS",
            rate=10.0,
        )
        data = self._run()

        # "First" carries the basic pay flag, so it is stored as the payslip's
        # own basic pay rather than as a row -- the two figures still have to
        # match, which is what this test is actually about.
        self.assertAlmostEqual(data["basic_pay"], PERIOD_CTC * 0.10, places=2)
        self.assertAlmostEqual(
            self._named(data["allowances"], "Second"), PERIOD_CTC * 0.10, places=2
        )

    def test_non_taxable_earnings_also_reduce_the_balance(self):
        """
        The balance is "what is left of the wage", and a non-taxable earning is
        still paid out of it. While the running total only counted taxable
        components, the parts summed to MORE than the stated total — which is
        the one invariant this mode exists to hold.
        """
        self._allowance(
            "Basic Pay", "BASIC", 10, is_fixed=True, amount=10000.0, is_basic_pay=True
        )
        non_taxable = Allowance.objects.create(
            title="Travel",
            code="TRAVEL",
            sequence=20,
            is_taxable=False,
            is_fixed=True,
            amount=2000.0,
        )
        non_taxable.specific_employees.add(self.employee)
        self._allowance(
            "Special Allowance", "SPECIAL", 900, is_fixed=False, based_on="balance"
        )
        data = self._run()

        total = data["basic_pay"] + sum(line["amount"] for line in data["allowances"])
        self.assertAlmostEqual(total, PERIOD_CTC, places=2)
        self.assertAlmostEqual(
            self._named(data["allowances"], "Special Allowance"),
            PERIOD_CTC - 12000.0,
            places=2,
        )


class CtcDownPayslipEditTests(CtcDownSetup, TestCase):
    """
    The payslip component editor reads every earning as a line and adds them
    up for gross. While basic pay was stored both as the payslip's figure and
    as its own row, that sum came to more than the payslip's own gross -- the
    editor offered a preview of 96,600 on a payslip whose gross was 69,000,
    and saving it would have written that.
    """

    def test_the_editor_adds_up_to_the_same_gross_the_payslip_has(self):
        from payroll.methods.methods import payslip_fields, save_payslip
        from payroll.methods.payslip_edit import editable_lines, preview_totals

        self._standard_structure()
        result = self._run()
        payslip = save_payslip(**payslip_fields(result, self.employee, status="draft"))

        totals = preview_totals(editable_lines(payslip), {}, set())
        self.assertAlmostEqual(totals["gross_pay"], payslip.gross_pay, places=2)

    def test_basic_pay_appears_once_in_the_editor(self):
        from payroll.methods.methods import payslip_fields, save_payslip
        from payroll.methods.payslip_edit import editable_lines

        self._standard_structure()
        result = self._run()
        payslip = save_payslip(**payslip_fields(result, self.employee, status="draft"))

        titles = [line["title"] for line in editable_lines(payslip)]
        self.assertEqual(titles.count("Basic Pay"), 1)

    def test_editing_basic_pay_moves_the_components_that_follow_it(self):
        """
        A CTC Down structure is a set of shares of one pot. Raising basic and
        leaving the rest where they were would produce a payslip no structure
        could have generated -- and, with a balance component absorbing the
        remainder, one whose parts no longer come to the CTC.
        """
        from payroll.methods.methods import payslip_fields, save_payslip
        from payroll.methods.payslip_edit import editable_lines, recompute_dependents

        self._standard_structure()
        result = self._run()
        payslip = save_payslip(**payslip_fields(result, self.employee, status="draft"))
        keys = {line["title"]: line["key"] for line in editable_lines(payslip)}

        raised = EXPECTED_BASIC + 1000.0
        amounts = recompute_dependents(payslip, {"basic": raised}, given={"basic"})

        # HRA is 40% of basic, so it follows.
        self.assertAlmostEqual(amounts[keys["HRA"]], raised * 0.40, places=2)
        # And the balance gives up exactly what the others took, so the parts
        # still come to the package.
        earnings = sum(
            amounts[key] for title, key in keys.items() if title != "Income Tax"
        )
        self.assertAlmostEqual(earnings, PERIOD_CTC, places=2)

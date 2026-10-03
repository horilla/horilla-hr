"""
What happens when more is owed than was earned.

A real payslip showed it: 23 days of loss of pay against 8 paid days on a
32,000 wage. Gross came to 33,440, the deductions to 36,480, and the payslip
showed all three — a taxable gross of **-3,040**, a deduction total larger
than the gross it came out of, and a net of zero that did not follow from
either.

Two rules now hold whatever the inputs:

  * taxable gross is never negative — there is no such thing as negative
    taxable pay, and a negative one is fed to the tax brackets and summed into
    every report that totals it;
  * total deductions never exceed gross — nobody is deducted more than they
    earned, and what could not be taken is carried on the payslip rather than
    dropped.

The second is a cap, not a floor on net: the figure stored on the payslip and
summed into a run's totals is what was actually taken.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.methods.payslip_calc import calculate_taxable_gross_pay
from payroll.models.models import Allowance, Contract, Deduction
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 8, 1)
END = date(2026, 8, 31)

# 8 days paid of 23 working days, the rest unpaid -- the shape of the payslip
# that prompted this.
MOSTLY_UNPAID = {
    "present": 8,
    "paid_leave": 0,
    "unpaid_leave": 15,
    "absent": 0,
    "week_off": 8,
    "holiday": 0,
    "total_working": 23,
    "unresolved_conflicts": 0,
}


class TaxableGrossTests(TestCase):
    """The floor, tested directly -- it is one subtraction."""

    def setUp(self):
        self.company = make_company("Cap Co")
        self.employee = make_employee(
            company=self.company, email="cap@test.horilla", first_name="Cap"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(
            self.employee, wage=32000.0, loss_of_pay_is_pretax=True
        )

    def taxable_gross(self, **overrides):
        kwargs = {
            "employee": self.employee,
            "start_date": START,
            "end_date": END,
            "basic_pay": 32000.0,
            "total_allowance": 1440.0,
            "allowances": {"allowances": []},
            "day_dict": {},
            "loss_of_pay_amount": 0.0,
        }
        kwargs.update(overrides)
        with patch(
            "payroll.methods.payslip_calc.calculate_pre_tax_deduction",
            return_value={"pretax_deductions": []},
        ):
            return calculate_taxable_gross_pay(**kwargs)["taxable_gross_pay"]

    def test_the_ordinary_case_is_untouched(self):
        self.assertAlmostEqual(self.taxable_gross(), 33440.0, places=2)

    def test_loss_of_pay_larger_than_the_pay_floors_at_zero(self):
        """
        Not -3,040. A negative taxable gross goes to the tax brackets and to
        every report that sums the column.
        """
        self.assertEqual(self.taxable_gross(loss_of_pay_amount=36480.0), 0.0)

    def test_loss_of_pay_exactly_equal_to_the_pay_gives_zero(self):
        self.assertEqual(self.taxable_gross(loss_of_pay_amount=33440.0), 0.0)


class DeductionCapTests(TestCase):
    """
    The cap, through the real engine -- the point is what lands on the payslip
    and in a run's totals, not what one function returns.
    """

    def setUp(self):
        self.company = make_company("Cap Co")
        self.employee = make_employee(
            company=self.company, email="capped@test.horilla", first_name="Capped"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(
            self.employee,
            wage=32000.0,
            deduct_leave_from_basic_pay=False,
            calculate_daily_leave_amount=True,
        )
        Allowance.objects.create(
            title="House Rent Allowance",
            is_fixed=True,
            amount=1440.0,
            include_active_employees=True,
            is_condition_based=False,
        )

    def run_payroll(self, summary=None):
        with patch(
            "payroll.methods.methods.get_leaves",
            return_value={
                "paid_leave": 0,
                "unpaid_leaves": 0,
                "partial_pay_days": 0,
                "total_leaves": 0,
                "paid_leave_dates": [],
                "unpaid_leave_dates": [],
                "custom_leave_dates": [],
                "custom_leave_breakdown": [],
                "leave_dates": [],
            },
        ):
            return payroll_calculation(
                self.employee, START, END, month_summary=summary or MOSTLY_UNPAID
            )

    def big_deduction(self, amount):
        Deduction.objects.create(
            title="Loan instalment",
            is_fixed=True,
            amount=amount,
            include_active_employees=True,
            is_condition_based=False,
            is_pretax=False,
        )

    def test_deductions_never_exceed_gross(self):
        self.big_deduction(99999.0)
        data = self.run_payroll()

        self.assertLessEqual(
            round(data["total_deductions"], 2), round(data["gross_pay"], 2)
        )

    def test_the_shortfall_is_the_difference(self):
        self.big_deduction(99999.0)
        data = self.run_payroll()

        self.assertAlmostEqual(
            data["uncovered_deduction"],
            round(data["deduction_before_cap"] - data["gross_pay"], 2),
            places=2,
        )

    def test_what_was_owed_is_kept_so_the_column_adds_up(self):
        """
        The payslip lists the component lines, then what could not be taken,
        then the total. Without the pre-cap figure the lines do not sum to the
        total shown beneath them.
        """
        self.big_deduction(99999.0)
        data = self.run_payroll()

        self.assertGreater(data["deduction_before_cap"], data["total_deductions"])
        self.assertAlmostEqual(
            data["total_deductions"] + data["uncovered_deduction"],
            data["deduction_before_cap"],
            places=2,
        )

    def test_net_pay_is_zero_and_follows_from_the_figures_shown(self):
        """
        The old payslip said 33,440 − 36,480 = 0, which is not true of any
        arithmetic. With the cap, gross minus the total shown is the net shown.
        """
        self.big_deduction(99999.0)
        data = self.run_payroll()

        self.assertEqual(data["net_pay"], 0.0)
        self.assertAlmostEqual(
            data["gross_pay"] - data["total_deductions"], data["net_pay"], places=2
        )

    def test_taxable_gross_is_not_negative_on_the_same_payslip(self):
        self.big_deduction(99999.0)
        data = self.run_payroll()
        self.assertGreaterEqual(data["taxable_gross_pay"], 0.0)

    def test_an_ordinary_payslip_is_not_capped(self):
        self.big_deduction(500.0)
        data = self.run_payroll()

        self.assertEqual(data["uncovered_deduction"], 0.0)
        self.assertAlmostEqual(
            data["deduction_before_cap"], data["total_deductions"], places=2
        )
        self.assertGreater(data["net_pay"], 0)

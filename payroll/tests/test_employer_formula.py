"""
The employer's share of a deduction, worked out by formula.

It could only ever be a percentage of whatever the deduction itself was based
on, and the rate field was only shown when that basis was a percentage-of
figure. So a component using a custom formula had no way to state an employer
contribution at all, and the cases that actually arise could not be expressed:

  * Provident fund, where the employer's 12% is split 8.33% to pension and
    3.67% to the fund, each capped separately.
  * A contribution reckoned on (BASIC + DA) while the employee's own share
    comes off BASIC alone.

These go through the real engine rather than calling the evaluator directly,
because the question is not "does the expression parse" — it is whether the
employer formula sees the same component amounts the employee side saw. Two
sides of one component reading different numbers is the failure that matters.
"""

import json
import logging
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.methods import calculate_employer_contribution
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 4, 1)
END = date(2026, 4, 30)

NO_LEAVE = {
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


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Employer Co")
        self.employee = make_employee(
            company=self.company, email="emp@test.horilla", first_name="Emp"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee, wage=30000.0)

        # BASIC 30,000 from the contract wage; DA a named earning on top, so a
        # formula has something to add to it that is not the wage.
        self.da = Allowance.objects.create(
            title="Dearness Allowance",
            code="DA",
            is_fixed=True,
            amount=6000.0,
            include_active_employees=True,
            is_condition_based=False,
            is_taxable=True,
        )

    def deduction(self, **overrides):
        defaults = dict(
            title="Provident Fund",
            code="PF",
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            include_active_employees=True,
            is_condition_based=False,
            is_pretax=True,
        )
        defaults.update(overrides)
        return Deduction.objects.create(**defaults)

    def payslip(self):
        """A real payslip, then the employer pass over it."""
        with patch("payroll.methods.methods.get_leaves", return_value=NO_LEAVE):
            result = payroll_calculation(self.employee, START, END)

        data = {"pay_data": json.loads(result["json_data"])}
        calculate_employer_contribution(data)
        return data["pay_data"]

    def contribution(self, pay_data, title):
        for key in (
            "pretax_deductions",
            "post_tax_deductions",
            "tax_deductions",
            "net_deductions",
        ):
            for row in pay_data.get(key) or []:
                if row.get("title") == title:
                    return row
        return None


class RateStillWorksTests(Fixture):
    def test_a_percentage_employer_share_is_unchanged(self):
        self.deduction(employer_rate=12.0)
        row = self.contribution(self.payslip(), "Provident Fund")

        self.assertAlmostEqual(
            row["employer_contribution_amount"], 30000.0 * 0.12, places=2
        )

    def test_no_employer_rate_means_no_contribution(self):
        self.deduction(employer_rate=0.0)
        row = self.contribution(self.payslip(), "Provident Fund")
        self.assertNotIn("employer_contribution_amount", row)


class FormulaTests(Fixture):
    def test_the_employer_share_can_be_a_formula(self):
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="(BASIC + DA) * 0.0367",
        )
        row = self.contribution(self.payslip(), "Provident Fund")

        self.assertAlmostEqual(
            row["employer_contribution_amount"], (30000.0 + 6000.0) * 0.0367, places=2
        )

    def test_the_formula_sees_what_the_employee_side_saw(self):
        """
        The point of carrying the component context onto the payslip. A
        formula evaluated against an empty context would silently return zero
        for every name in it — which reads exactly like "no contribution".
        """
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="DA",
        )
        pay_data = self.payslip()
        row = self.contribution(pay_data, "Provident Fund")

        self.assertEqual(pay_data["component_context"]["DA"], 6000.0)
        self.assertAlmostEqual(row["employer_contribution_amount"], 6000.0, places=2)

    def test_a_formula_can_use_the_engines_own_names(self):
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="GROSS * 0.02",
        )
        pay_data = self.payslip()
        row = self.contribution(pay_data, "Provident Fund")

        self.assertAlmostEqual(
            row["employer_contribution_amount"],
            pay_data["component_context"]["GROSS"] * 0.02,
            places=2,
        )

    def test_min_and_max_work_so_a_cap_can_be_expressed(self):
        """
        The case a plain rate cannot state: 3.67% of (BASIC + DA), capped.
        """
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="min((BASIC + DA) * 0.0367, 550)",
        )
        row = self.contribution(self.payslip(), "Provident Fund")
        self.assertAlmostEqual(row["employer_contribution_amount"], 550.0, places=2)

    def test_a_formula_applies_to_a_fixed_amount_component_too(self):
        """
        The rate field was only shown for percentage-of components, so a flat
        deduction could not carry an employer share at all.
        """
        self.deduction(
            is_fixed=True,
            amount=1800.0,
            based_on=None,
            rate=None,
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="BASIC * 0.0833",
        )
        row = self.contribution(self.payslip(), "Provident Fund")
        self.assertAlmostEqual(
            row["employer_contribution_amount"], 30000.0 * 0.0833, places=2
        )

    def test_two_components_can_split_one_statutory_rate(self):
        """
        What the whole thing is for: an employer's 12% split 8.33% to pension
        and 3.67% to the fund, each stated on its own row.
        """
        self.deduction(
            title="PF - Fund",
            code="PFF",
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="BASIC * 0.0367",
        )
        self.deduction(
            title="PF - Pension",
            code="PFP",
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="min(BASIC, 15000) * 0.0833",
        )
        pay_data = self.payslip()

        fund = self.contribution(pay_data, "PF - Fund")
        pension = self.contribution(pay_data, "PF - Pension")

        self.assertAlmostEqual(
            fund["employer_contribution_amount"], 30000.0 * 0.0367, places=2
        )
        self.assertAlmostEqual(
            pension["employer_contribution_amount"], 15000.0 * 0.0833, places=2
        )


class BrokenFormulaTests(Fixture):
    def test_a_broken_formula_does_not_stop_the_payslip(self):
        """
        The employer's share is the employer's problem. A mistyped expression
        there must not be the reason someone is not paid.
        """
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="BASIC * * 2",
        )
        pay_data = self.payslip()
        row = self.contribution(pay_data, "Provident Fund")

        self.assertIsNotNone(row)
        self.assertNotIn("employer_contribution_amount", row)
        self.assertGreater(pay_data["net_pay"], 0)

    def test_an_unknown_name_contributes_nothing_rather_than_failing(self):
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="NOT_A_COMPONENT * 0.5",
        )
        row = self.contribution(self.payslip(), "Provident Fund")
        self.assertEqual(row["employer_contribution_amount"], 0.0)

    def test_an_empty_formula_is_skipped(self):
        self.deduction(
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA, employer_formula=""
        )
        row = self.contribution(self.payslip(), "Provident Fund")
        self.assertNotIn("employer_contribution_amount", row)

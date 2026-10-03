"""
PAID_DAYS, UNPAID_DAYS and LOP as names a component formula can use.

A structure that wants a deduction to react to attendance -- "(BASIC - LOP) *
0.12", say, to reproduce the old deduct_leave_from_basic_pay behaviour for
just that one component -- had no way to say so: component_context only ever
carried BASIC/GROSS/CTC/EARNED, so LOP silently read as 0 in a formula.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Contract, Deduction
from payroll.tests.factories_payroll import make_active_contract

START = date(2024, 1, 1)
END = date(2024, 1, 31)

LEAVE_DATA = {
    "paid_leave": 0,
    "unpaid_leaves": 3,
    "partial_pay_days": 0,
    "total_leaves": 3,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}


class Fixture(TestCase):
    def setUp(self):
        company = make_company("Formula Context Co")
        self.employee = make_employee(
            company=company, email="formula-context@test.horilla"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee, wage=30000.0)

    def deduction(self, formula, **overrides):
        defaults = dict(
            title="Custom",
            is_fixed=False,
            based_on="formula",
            formula=formula,
            include_active_employees=True,
            is_condition_based=False,
            is_pretax=False,
        )
        defaults.update(overrides)
        deduction = Deduction.objects.create(**defaults)
        return deduction

    def result(self):
        with patch(
            "payroll.methods.methods.months_between_range",
            return_value=[{"working_days_on_period": 22, "per_day_amount": 1000.0}],
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=LEAVE_DATA
        ):
            data = payroll_calculation(self.employee, START, END)
        return json.loads(data["json_data"])

    def row(self, pay_data, title):
        for row in pay_data.get("post_tax_deductions") or []:
            if row.get("title") == title:
                return row
        return None


class FormulaContextTests(Fixture):
    def test_lop_is_available_to_a_formula(self):
        self.deduction("LOP", title="Reads LOP")
        row = self.row(self.result(), "Reads LOP")
        # unpaid_leaves(3) * day_wage(1000) = 3000, exactly loss_of_pay.
        self.assertAlmostEqual(row["amount"], 3000.0, places=2)

    def test_unpaid_days_is_available_to_a_formula(self):
        self.deduction("UNPAID_DAYS * 100", title="Reads unpaid days")
        row = self.row(self.result(), "Reads unpaid days")
        self.assertAlmostEqual(row["amount"], 300.0, places=2)

    def test_paid_days_is_available_to_a_formula(self):
        self.deduction("PAID_DAYS * 10", title="Reads paid days")
        row = self.row(self.result(), "Reads paid days")
        # 22 working days - 3 unpaid = 19 paid days.
        self.assertAlmostEqual(row["amount"], 190.0, places=2)

    def test_an_unrelated_formula_is_unaffected(self):
        """LOP/PAID_DAYS/UNPAID_DAYS are additive -- a formula that never
        names them keeps reading exactly the components it already did."""
        self.deduction("BASIC * 0.1", title="Basic-only")
        row = self.row(self.result(), "Basic-only")
        # basic_pay = (22 working days * 1000/day) - loss_of_pay(3000), since
        # the fixture contract's deduct_leave_from_basic_pay defaults to True.
        self.assertAlmostEqual(row["amount"], 1900.0, places=2)


class FormulaDeductionValidationTests(TestCase):
    """
    Deduction.clean()'s "Employee rate must be specified" check used to fire
    for every non-fixed based_on, formula included -- but a formula carries
    its own arithmetic ("(BASIC - LOP) * 0.12") and has no use for a
    separate percentage field, so requiring one made a formula-based
    deduction impossible to save at all.
    """

    def test_a_formula_deduction_does_not_need_a_rate(self):
        deduction = Deduction(
            title="Custom",
            is_fixed=False,
            based_on="formula",
            formula="(BASIC - LOP) * 0.12",
        )
        deduction.full_clean(exclude=["created_by", "modified_by"])

    def test_a_percentage_deduction_still_needs_a_rate(self):
        """The validation itself isn't gone -- only exempted for formula."""
        deduction = Deduction(
            title="Custom",
            is_fixed=False,
            based_on="basic_pay",
        )
        with self.assertRaises(ValidationError):
            deduction.full_clean(exclude=["created_by", "modified_by"])

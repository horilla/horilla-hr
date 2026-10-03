"""
"When it applies" rules.

Two limits sat on this gate. It could only measure basic pay on an allowance
and basic-or-gross on a deduction, and there could only ever be one rule — so
"ESI applies while gross is at or under 21,000, and only above a basic floor"
was two conditions with room for one.

Which measures a component may be gated on is not a free choice. Gross is basic
plus the allowances and net is what survives the deductions, so while an
allowance is being worked out neither figure exists yet; if_condition_on left
gross at 0 for allowances, which is why offering it there would have compared
against zero and silently paid nothing. These pin down what each component type
may measure, and that every rule has to hold.

A rule that does not hold sets the component to 0; it does not drop it from the
payslip. That is the long-standing behaviour of if_condition_on and the golden
suite is built on it, so these assert a zero line rather than an absent one.
"""

from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, ApplyCondition, Contract, Deduction
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

WORKING_DAYS = 22
PER_DAY = 1000.0
PERIOD_WAGE = WORKING_DAYS * PER_DAY  # 22,000
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


class ApplyConditionSetup:
    def setUp(self):
        company = make_company("Gate Co")
        self.employee = make_employee(company=company, email="gate@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def _allowance(self, title, **kw):
        kw.setdefault("is_taxable", True)
        allowance = Allowance.objects.create(title=title, **kw)
        allowance.specific_employees.add(self.employee)
        return allowance

    def _deduction(self, title, **kw):
        deduction = Deduction.objects.create(title=title, **kw)
        deduction.specific_employees.add(self.employee)
        return deduction

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
        return next((line["amount"] for line in lines if line["title"] == title), None)

    def _deducted(self, data, title):
        for bucket in ("pretax_deductions", "post_tax_deductions", "tax_deductions"):
            found = self._named(data.get(bucket, []), title)
            if found is not None:
                return found
        return None


class SingleRuleTests(ApplyConditionSetup, TestCase):
    def test_a_deduction_can_be_gated_on_gross(self):
        """
        The case that started this: ESI applies only up to a gross ceiling.
        Gross here is 22,000, so a 21,000 ceiling has to exclude it.
        """
        self._deduction(
            "ESI",
            is_fixed=True,
            amount=500.0,
            if_choice="gross_pay",
            if_condition="le",
            if_amount=21000.0,
        )
        self.assertEqual(self._deducted(self._run(), "ESI"), 0)

    def test_the_same_gate_lets_it_through_under_the_ceiling(self):
        self._deduction(
            "ESI",
            is_fixed=True,
            amount=500.0,
            if_choice="gross_pay",
            if_condition="le",
            if_amount=25000.0,
        )
        self.assertEqual(self._deducted(self._run(), "ESI"), 500.0)

    def test_a_component_can_be_gated_on_another_component(self):
        top_up = self._allowance("Top Up", is_fixed=True, amount=2000.0, sequence=10)
        self._allowance(
            "Bonus",
            is_fixed=True,
            amount=750.0,
            sequence=20,
            if_choice="component",
            if_component_code=top_up.code,
            if_condition="ge",
            if_amount=2000.0,
        )
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 750.0)

    def test_a_component_gate_that_does_not_hold_pays_nothing(self):
        top_up = self._allowance("Top Up", is_fixed=True, amount=100.0, sequence=10)
        self._allowance(
            "Bonus",
            is_fixed=True,
            amount=750.0,
            sequence=20,
            if_choice="component",
            if_component_code=top_up.code,
            if_condition="ge",
            if_amount=2000.0,
        )
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 0)


class ManyRuleTests(ApplyConditionSetup, TestCase):
    def test_every_rule_has_to_hold(self):
        """
        A second rule narrows the component. Were these OR-ed, the failing rule
        below would be masked by the passing one and the bonus would be paid.
        """
        allowance = self._allowance("Bonus", is_fixed=True, amount=900.0)
        allowance.apply_conditions.add(
            ApplyCondition.objects.create(
                choice="basic_pay", condition="gt", amount=0.0
            ),
            ApplyCondition.objects.create(
                choice="basic_pay", condition="gt", amount=PERIOD_WAGE * 10
            ),
        )
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 0)

    def test_a_component_is_paid_when_all_of_its_rules_hold(self):
        allowance = self._allowance("Bonus", is_fixed=True, amount=900.0)
        allowance.apply_conditions.add(
            ApplyCondition.objects.create(
                choice="basic_pay", condition="gt", amount=0.0
            ),
            ApplyCondition.objects.create(
                choice="basic_pay", condition="lt", amount=PERIOD_WAGE * 10
            ),
        )
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 900.0)

    def test_a_range_rule_uses_both_bounds(self):
        allowance = self._allowance("Bonus", is_fixed=True, amount=900.0)
        allowance.apply_conditions.add(
            ApplyCondition.objects.create(
                choice="basic_pay",
                condition="range",
                start_range=0.0,
                end_range=PERIOD_WAGE - 1,
            )
        )
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 0)

    def test_a_component_with_no_extra_rules_is_unaffected(self):
        """The overwhelmingly common case, and what the golden suite covers."""
        self._allowance("Bonus", is_fixed=True, amount=900.0)
        self.assertEqual(self._named(self._run()["allowances"], "Bonus"), 900.0)


class ApplyChoiceAvailabilityTests(TestCase):
    """What each component type may be measured against, and why they differ."""

    def test_an_allowance_is_not_offered_a_measure_that_does_not_exist_yet(self):
        offered = {value for value, _label in Allowance.if_condition_choice}
        self.assertNotIn("gross_pay", offered)
        self.assertNotIn("taxable_gross_pay", offered)
        self.assertNotIn("net_pay", offered)

    def test_a_deduction_may_be_measured_against_the_earnings_totals(self):
        offered = {value for value, _label in Deduction.if_condition_choice}
        self.assertIn("gross_pay", offered)
        self.assertIn("taxable_gross_pay", offered)

    def test_both_may_be_measured_against_basic_ctc_or_a_component(self):
        for model in (Allowance, Deduction):
            with self.subTest(model=model.__name__):
                offered = {value for value, _label in model.if_condition_choice}
                self.assertTrue({"basic_pay", "ctc", "component"} <= offered)

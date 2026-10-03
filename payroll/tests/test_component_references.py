"""
Cross-component references and formulas.

Before this, every amount strategy was hardwired to a fixed aggregate — basic
pay for an allowance; basic/gross/taxable/net for a deduction — so one
component could never be stated in terms of another. "HRA = 50% of BASIC" and
"PF = 12% of (BASIC + DA)", the two most ordinary rules in Indian payroll, were
both inexpressible without writing Python.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

WORKING_DAYS = 22
PER_DAY = 1000.0
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


class ComponentReferenceTests(TestCase):
    def setUp(self):
        company = make_company("Ref Co")
        self.employee = make_employee(company=company, email="ref@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def _allowance(self, title, code, sequence, **kw):
        allowance = Allowance.objects.create(
            title=title, code=code, sequence=sequence, is_taxable=True, **kw
        )
        allowance.specific_employees.add(self.employee)
        return allowance

    def _deduction(self, title, code, sequence, **kw):
        deduction = Deduction.objects.create(
            title=title, code=code, sequence=sequence, **kw
        )
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
        return next(line["amount"] for line in lines if line["title"] == title)

    def test_percentage_of_another_component(self):
        """The canonical case: HRA is a percentage of basic, by name."""
        self._allowance(
            "HRA",
            "HRA",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=50.0,
        )
        data = self._run()
        self.assertAlmostEqual(
            self._named(data["allowances"], "HRA"), data["basic_pay"] * 0.5, places=2
        )

    def test_a_component_can_reference_an_earlier_component(self):
        """Not just the period figures — another component's own amount."""
        self._allowance(
            "DA",
            "DA",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=10.0,
        )
        self._allowance(
            "On DA",
            "ONDA",
            30,
            is_fixed=False,
            based_on="component",
            percentage_of_code="DA",
            rate=50.0,
        )
        data = self._run()
        da = self._named(data["allowances"], "DA")
        self.assertAlmostEqual(
            self._named(data["allowances"], "On DA"), da * 0.5, places=2
        )

    def test_formula_over_several_components(self):
        """PF on a wage base of BASIC + DA — expressible without code."""
        self._allowance(
            "DA",
            "DA",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=10.0,
        )
        self._deduction(
            "PF",
            "PF",
            30,
            is_pretax=True,
            is_fixed=False,
            based_on="formula",
            formula="(BASIC + DA) * 0.12",
        )
        data = self._run()
        basic = data["basic_pay"]
        self.assertAlmostEqual(
            self._named(data["pretax_deductions"], "PF"),
            (basic + basic * 0.1) * 0.12,
            places=2,
        )

    def test_a_deduction_can_reference_gross(self):
        """
        GROSS is seeded from basic and grows through the earnings pass, so by
        the time a deduction runs it is the real gross — not the allowances
        alone, which is what an empty seed produced.
        """
        self._allowance("Bonus", "BONUS", 20, is_fixed=True, amount=6000.0)
        self._deduction(
            "ESI",
            "ESI",
            30,
            is_pretax=True,
            is_fixed=False,
            based_on="component",
            percentage_of_code="GROSS",
            rate=0.75,
        )
        data = self._run()
        self.assertAlmostEqual(
            self._named(data["pretax_deductions"], "ESI"),
            data["gross_pay"] * 0.0075,
            places=2,
        )

    def test_sequence_decides_what_is_visible(self):
        """
        A component that runs before its target sees nothing and contributes 0,
        rather than aborting the payslip — the same stance the formula
        evaluator takes for an unknown name.
        """
        self._allowance(
            "Too Early",
            "EARLY",
            10,
            is_fixed=False,
            based_on="component",
            percentage_of_code="LATE",
            rate=50.0,
        )
        self._allowance("Later", "LATE", 90, is_fixed=True, amount=5000.0)
        data = self._run()
        self.assertEqual(self._named(data["allowances"], "Too Early"), 0)
        self.assertEqual(self._named(data["allowances"], "Later"), 5000.0)

    def test_unknown_code_contributes_nothing(self):
        self._allowance(
            "Dangling",
            "DANGLING",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="NOSUCHCODE",
            rate=50.0,
        )
        self.assertEqual(self._named(self._run()["allowances"], "Dangling"), 0)

    def test_a_component_without_a_code_still_computes(self):
        """Codes are optional — only referenced components need one."""
        self._allowance("Plain", "", 20, is_fixed=True, amount=1234.0)
        self.assertEqual(self._named(self._run()["allowances"], "Plain"), 1234.0)

    def test_max_limit_still_caps_a_referenced_percentage(self):
        self._allowance(
            "Capped HRA",
            "CAPPED",
            20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=50.0,
            has_max_limit=True,
            maximum_amount=5000.0,
        )
        self.assertEqual(self._named(self._run()["allowances"], "Capped HRA"), 5000.0)


class ReservedCodeTests(TestCase):
    """
    The engine publishes GROSS and CTC itself, so no component may answer to
    those names. An allowance titled "Gross" derived the code GROSS and
    replaced the real figure partway through the pass, which moved every
    percentage of gross configured after it and left no trace of why.

    BASIC is deliberately not reserved: a CTC Down structure derives basic pay
    from a component, so that one is meant to be written.
    """

    def setUp(self):
        company = make_company("Reserved Co")
        self.employee = make_employee(company=company, email="reserved@test.horilla")

    def test_a_component_named_gross_does_not_take_the_engines_code(self):
        for title, taken in (("Gross", "GROSS"), ("CTC", "CTC")):
            with self.subTest(title=title):
                component = Allowance.objects.create(
                    title=title, is_fixed=True, amount=1
                )
                self.assertNotEqual(component.code, taken)
                self.assertTrue(component.code.startswith(taken))

    def test_basic_is_still_derivable(self):
        self.assertEqual(
            Allowance.objects.create(title="Basic", is_fixed=True, amount=1).code,
            "BASIC",
        )

    def test_the_context_refuses_a_reserved_code_even_if_one_is_stored(self):
        """Defence at the point of harm, for a row that predates the rule."""
        from payroll.methods.component_engine import new_context, record

        context = new_context(0.0, total_gross=50000.0)
        stale = Allowance(title="Gross", code="GROSS", is_fixed=True, amount=1)
        record(context, stale, 999.0)
        self.assertEqual(context["GROSS"], 50000.0)

"""
Golden (characterization) suite for ``payroll_calculation()``.

This is the safety net for the payroll engine rework. There is no other
end-to-end test of the engine: the existing payroll tests are unit-level and
use ``SimpleNamespace`` fakes, so they cannot see list ordering, per-line
attribution, or the interaction between the six deduction phases — which is
exactly what the rework touches.

Each scenario asserts the **entire** persisted payslip payload, not just net
pay. Net pay alone would happily stay correct while amounts landed on the wrong
deduction lines.

Regenerating the baseline
-------------------------
    HORILLA_GOLDEN_WRITE=1 python manage.py test payroll.tests.test_payroll_calculation_golden

writes ``payroll/tests/golden/payroll_calculation.json`` instead of asserting.
Never hand-edit that file, and never regenerate it casually: a diff in it means
computed pay changed. Only a commit that *intends* to change pay may carry one,
and it should carry nothing else.

Determinism
-----------
``compute_salary_on_period`` reads working-day calendars, holidays and leave,
none of which are stable across machines or clock dates. Those three inputs are
patched to fixed values — the same approach ``test_compute_salary_on_period.py``
takes, and that function has its own dedicated tests. Everything downstream of
basic pay (components, phases, tax) runs for real.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Contract
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
    make_allowance,
    make_deduction,
    make_filing_status,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "payroll_calculation.json"
WRITE_MODE = bool(os.environ.get("HORILLA_GOLDEN_WRITE"))

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

# Component rows are created fresh per test, so their primary keys differ every
# run and cannot be baselined. Dropping the ids is safe for what this suite
# guards: every line still carries its own ``title``, so a title-to-amount
# mismatch (the zip() misattribution) is still caught exactly.
VOLATILE_KEYS = {"allowance_id", "deduction_id", "id", "employee"}


def _normalize(value):
    """Strip run-varying primary keys, leaving titles and amounts intact."""
    if isinstance(value, dict):
        return {
            key: (None if key in VOLATILE_KEYS else _normalize(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


class PayrollCalculationGoldenTests(TestCase):
    """One scenario per method; all share the same period and wage."""

    maxDiff = None
    _written: dict = {}

    def setUp(self):
        company = make_company("Golden Co")
        self.employee = make_employee(company=company, email="golden@test.horilla")
        # make_employee's own contract (if any) would compete for "active".
        Contract.objects.filter(employee_id=self.employee).delete()

    # -- harness ----------------------------------------------------------

    def _run(self):
        """Run the engine with salary-period inputs pinned."""
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
            data = payroll_calculation(self.employee, PERIOD_START, PERIOD_END)
        self.assertIsNotNone(data, "engine returned no payslip data")
        # json_data is what actually lands in Payslip.pay_head_data.
        return _normalize(json.loads(data["json_data"]))

    def _assert_golden(self, name):
        actual = self._run()
        if WRITE_MODE:
            type(self)._written[name] = actual
            return
        self.assertTrue(
            GOLDEN_PATH.exists(),
            f"{GOLDEN_PATH} is missing — regenerate with HORILLA_GOLDEN_WRITE=1",
        )
        baseline = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertIn(name, baseline, f"no baseline for scenario {name!r}")
        self.assertEqual(baseline[name], actual)

    @classmethod
    def tearDownClass(cls):
        if WRITE_MODE and cls._written:
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if GOLDEN_PATH.exists():
                existing = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
            existing.update(cls._written)
            GOLDEN_PATH.write_text(
                json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"\n[golden] wrote {len(cls._written)} scenario(s) to {GOLDEN_PATH}")
        super().tearDownClass()

    # -- scenarios --------------------------------------------------------

    def test_bare_contract(self):
        """No components at all — the floor case."""
        make_active_contract(self.employee)
        self._assert_golden("bare_contract")

    def test_fixed_allowances_taxable_and_not(self):
        """Ordering here is what the sequence backfill must preserve."""
        make_active_contract(self.employee)
        make_allowance(self.employee, "Taxable Fixed", amount=2000.0, is_taxable=True)
        make_allowance(self.employee, "Untaxed Fixed", amount=750.0, is_taxable=False)
        self._assert_golden("fixed_allowances_taxable_and_not")

    def test_percentage_of_basic_allowance(self):
        """The only percentage base an Allowance can currently use."""
        make_active_contract(self.employee)
        make_allowance(
            self.employee,
            "HRA",
            is_fixed=False,
            based_on="basic_pay",
            rate=50.0,
        )
        self._assert_golden("percentage_of_basic_allowance")

    def test_percentage_of_basic_with_max_limit(self):
        make_active_contract(self.employee)
        make_allowance(
            self.employee,
            "Capped HRA",
            is_fixed=False,
            based_on="basic_pay",
            rate=50.0,
            has_max_limit=True,
            maximum_amount=5000.0,
        )
        self._assert_golden("percentage_of_basic_with_max_limit")

    def test_pretax_deduction_percentage_of_gross(self):
        make_active_contract(self.employee)
        make_allowance(self.employee, "Fixed Allowance", amount=2000.0)
        make_deduction(
            self.employee,
            "PF",
            is_pretax=True,
            is_fixed=False,
            based_on="gross_pay",
            rate=12.0,
        )
        self._assert_golden("pretax_deduction_percentage_of_gross")

    def test_post_tax_deduction_fixed(self):
        make_active_contract(self.employee)
        make_deduction(self.employee, "Canteen", amount=300.0)
        self._assert_golden("post_tax_deduction_fixed")

    def test_post_tax_net_pay_deduction_ordering(self):
        """
        The zip() misattribution case.

        ``calculate_post_tax_deduction`` appends to the component list but not
        the amount list for a ``net_pay``-based deduction, then re-pairs the two
        with zip() — and separately emits the same deduction into
        ``net_deductions``. With a net_pay deduction sitting *before* two others,
        the baseline captures both the misattribution and the double-count, so
        the later fix shows up as an explicit, reviewable diff.
        """
        make_active_contract(self.employee)
        make_deduction(
            self.employee,
            "A Net Based",
            is_fixed=False,
            based_on="net_pay",
            rate=10.0,
        )
        make_deduction(self.employee, "B Fixed Post Tax", amount=400.0)
        make_deduction(self.employee, "C Fixed Post Tax", amount=600.0)
        self._assert_golden("post_tax_net_pay_deduction_ordering")

    def test_tax_deduction_flagged(self):
        """
        Regression guard: a *fixed* tax deduction used to crash the whole run.

        ``calculate_tax_deduction`` was the only gatherer of the four without an
        ``is_fixed`` branch, so it called ``calculation_mapping.get(None)`` --
        ``Deduction.based_on`` has no default -- and every payslip generation
        raised "'NoneType' object is not callable". A flat Professional Tax is
        exactly this shape.
        """
        make_active_contract(self.employee)
        make_deduction(
            self.employee,
            "Professional Tax",
            is_tax=True,
            is_pretax=False,
            amount=200.0,
        )
        self._assert_golden("tax_deduction_flagged")

    def test_federal_tax_brackets(self):
        """Progressive bands, annualized then pro-rated back to the period."""
        status = make_filing_status(
            "Golden Progressive",
            brackets=[(0, 120000, 10.0), (120000, 480000, 20.0)],
        )
        make_active_contract(self.employee, filing_status=status)
        make_allowance(self.employee, "Fixed Allowance", amount=2000.0)
        self._assert_golden("federal_tax_brackets")

    def test_no_filing_status_yields_zero_tax(self):
        """Today's silent zero — baselined so the A1 fix is a visible diff."""
        make_active_contract(self.employee, filing_status=None)
        self._assert_golden("no_filing_status_yields_zero_tax")

    def test_update_compensation_on_basic(self):
        make_active_contract(self.employee)
        make_deduction(
            self.employee,
            "Basic Adjustment",
            update_compensation="basic_pay",
            amount=1500.0,
        )
        self._assert_golden("update_compensation_on_basic")

    def test_update_compensation_on_gross(self):
        make_active_contract(self.employee)
        make_allowance(self.employee, "Fixed Allowance", amount=2000.0)
        make_deduction(
            self.employee,
            "Gross Adjustment",
            update_compensation="gross_pay",
            amount=1200.0,
        )
        self._assert_golden("update_compensation_on_gross")

    def test_update_compensation_on_net(self):
        make_active_contract(self.employee)
        make_deduction(
            self.employee, "Net Adjustment", update_compensation="net_pay", amount=900.0
        )
        self._assert_golden("update_compensation_on_net")

    def test_lop_held_back_from_gross(self):
        """``deduct_leave_from_basic_pay=False`` — LOP as one lump off gross."""
        make_active_contract(self.employee, deduct_leave_from_basic_pay=False)
        make_allowance(self.employee, "Fixed Allowance", amount=2000.0)
        self._assert_golden("lop_held_back_from_gross")

    def test_daily_wage_type(self):
        make_active_contract(self.employee, wage_type="daily", wage=800.0)
        self._assert_golden("daily_wage_type")

    def test_one_time_allowance_inside_period(self):
        make_active_contract(self.employee)
        make_allowance(
            self.employee, "Bonus", amount=5000.0, one_time_date=date(2024, 1, 15)
        )
        self._assert_golden("one_time_allowance_inside_period")

    def test_one_time_allowance_outside_period(self):
        make_active_contract(self.employee)
        make_allowance(
            self.employee, "Stale Bonus", amount=5000.0, one_time_date=date(2023, 12, 1)
        )
        self._assert_golden("one_time_allowance_outside_period")

    def test_non_taxable_allowance_excluded_from_taxable_gross(self):
        status = make_filing_status("Golden Flat", brackets=[(0, 1200000, 15.0)])
        make_active_contract(self.employee, filing_status=status)
        make_allowance(self.employee, "Taxable Part", amount=3000.0, is_taxable=True)
        make_allowance(self.employee, "Untaxed Part", amount=3000.0, is_taxable=False)
        self._assert_golden("non_taxable_allowance_excluded_from_taxable_gross")

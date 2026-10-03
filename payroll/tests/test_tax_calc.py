"""
Tests for payroll.methods.tax_calc.

There were none before: nothing covered bracket selection, the
annualize/de-annualize round trip, use_py dispatch, or — most importantly — the
``except Exception: logger.error(e)`` path that turned any broken tax formula
into a silent 0 and a payslip that overpaid without saying so.
"""

from datetime import date

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.tax_calc import TaxComputationError, calculate_taxable_amount
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract, make_filing_status

WORKING = "def calculate_federal_tax(yearly_income):\n    return yearly_income * 0.1\n"
HANGS = "def calculate_federal_tax(yearly_income):\n    while True:\n        pass\n"
RAISES = "def calculate_federal_tax(yearly_income):\n    return 1 / 0\n"

PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2024, 1, 31)


class TaxComputationErrorTests(TestCase):
    """A filing status that is *configured* to compute tax must never quietly
    return 0 when it cannot."""

    def setUp(self):
        company = make_company("Tax Co")
        self.employee = make_employee(company=company, email="tax@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _calculate(self, filing_status):
        make_active_contract(self.employee, filing_status=filing_status)
        return calculate_taxable_amount(
            employee=self.employee,
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            basic_pay=30000.0,
            day_dict={},
            allowances={"allowances": []},
            total_allowance=0,
            gross_pay=30000.0,
        )

    def test_empty_python_code_raises(self):
        """
        The most common real failure: the editor writes python_code through a
        postMessage callback, so saving before it fires stores "" while use_py
        stays on. This used to tax every payslip at 0.
        """
        status = make_filing_status("Empty Code", use_py=True, python_code="")
        with self.assertRaises(TaxComputationError) as ctx:
            self._calculate(status)
        self.assertIn("Empty Code", str(ctx.exception))
        self.assertIn("empty", str(ctx.exception).lower())

    def test_formula_that_raises_is_reported(self):
        status = make_filing_status("Divides By Zero", use_py=True, python_code=RAISES)
        with self.assertRaises(TaxComputationError) as ctx:
            self._calculate(status)
        self.assertIn("ZeroDivisionError", str(ctx.exception))

    def test_runaway_formula_times_out_and_is_reported(self):
        """An unbounded formula used to hang payroll generation outright."""
        status = make_filing_status("Runaway", use_py=True, python_code=HANGS)
        with self.assertRaises(TaxComputationError) as ctx:
            self._calculate(status)
        self.assertIn("Runaway", str(ctx.exception))

    def test_error_message_names_the_employee_and_the_remedy(self):
        status = make_filing_status("Broken", use_py=True, python_code=RAISES)
        with self.assertRaises(TaxComputationError) as ctx:
            self._calculate(status)
        message = str(ctx.exception)
        self.assertIn(str(self.employee), message)
        self.assertIn("Python mode", message)

    def test_working_formula_still_computes(self):
        """The guard must not fire on a healthy formula."""
        status = make_filing_status("Healthy", use_py=True, python_code=WORKING)
        self.assertGreater(self._calculate(status), 0)

    def test_no_filing_status_is_not_an_error(self):
        """
        Unset is a legitimate configuration meaning "no income tax for this
        employee" — plenty of tenants model tax with Deduction(is_tax=True)
        instead — so it must stay a quiet 0, not become an error.
        """
        self.assertEqual(self._calculate(None), 0)

    def test_bracket_mode_is_unaffected_by_the_guard(self):
        status = make_filing_status(
            "Progressive", brackets=[(0, 120000, 10.0), (120000, 480000, 20.0)]
        )
        self.assertGreater(self._calculate(status), 0)


class DeclarativeAdjustmentTests(TestCase):
    """
    Standard deduction, rebate and cess — the three primitives that let a real
    tax system be expressed as configuration instead of code.

    They matter because the Python template this app ships is 70 lines that
    reimplement the bracket table, so the only reason most tenants ever reached
    for code was a rule the data model could not express.

    A full calendar year is used as the period so annualisation is 1:1 and the
    figures below are directly comparable to published tax tables.
    """

    def setUp(self):
        company = make_company("Adjust Co")
        self.employee = make_employee(company=company, email="adjust@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _tax(self, filing_status, yearly):
        make_active_contract(self.employee, filing_status=filing_status)
        return calculate_taxable_amount(
            employee=self.employee,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            basic_pay=yearly,
            day_dict={},
            allowances={"allowances": []},
            total_allowance=0,
            gross_pay=yearly,
        )

    def _india_new_regime(self):
        return make_filing_status(
            "India New Regime",
            based_on="basic_pay",
            standard_deduction=75000,
            rebate_income_limit=1200000,
            rebate_max_amount=60000,
            cess_percent=4.0,
            brackets=[
                (0, 400000, 0),
                (400000, 800000, 5),
                (800000, 1200000, 10),
                (1200000, 1600000, 15),
                (1600000, 9999999999, 20),
            ],
        )

    def test_standard_deduction_reduces_taxable_income(self):
        status = make_filing_status(
            "Flat With Deduction",
            based_on="basic_pay",
            standard_deduction=50000,
            brackets=[(0, 9999999999, 10)],
        )
        # 200000 - 50000 = 150000 taxable at 10%
        self.assertAlmostEqual(self._tax(status, 200000), 15000.0, places=2)

    def test_rebate_cancels_tax_at_or_below_the_limit(self):
        """India's 12.75L salaried nil-tax outcome, entirely from configuration."""
        self.assertAlmostEqual(
            self._tax(self._india_new_regime(), 1275000), 0.0, places=2
        )

    def test_rebate_does_not_apply_above_the_limit(self):
        """
        One rupee of income over the threshold and the full slab tax applies —
        the cliff edge is the actual behaviour of the rule, so it is asserted
        rather than smoothed.
        """
        self.assertGreater(self._tax(self._india_new_regime(), 1275100), 0.0)

    def test_cess_is_applied_on_top_of_tax(self):
        """20L: 185,000 of slab tax, plus 4% cess = 192,400."""
        self.assertAlmostEqual(
            self._tax(self._india_new_regime(), 2000000), 192400.0, places=2
        )

    def test_rebate_is_applied_before_cess(self):
        """
        A cess is levied on tax actually payable after relief. If cess were
        applied first the rebate would be cancelling an inflated figure.
        """
        status = self._india_new_regime()
        self.assertAlmostEqual(self._tax(status, 1275000), 0.0, places=2)

    def test_defaults_are_a_no_op(self):
        """
        Every adjustment defaults to nothing, so an existing filing status
        computes exactly as it did before these fields existed.
        """
        plain = make_filing_status(
            "Plain", based_on="basic_pay", brackets=[(0, 9999999999, 10)]
        )
        self.assertAlmostEqual(self._tax(plain, 200000), 20000.0, places=2)

    def test_adjustments_also_apply_in_python_mode(self):
        """Both modes are first-class, so both get the adjustments."""
        status = make_filing_status(
            "Python With Adjustments",
            based_on="basic_pay",
            use_py=True,
            python_code=WORKING,
            standard_deduction=50000,
            cess_percent=10.0,
        )
        # (200000 - 50000) * 10% = 15000, + 10% cess = 16500
        self.assertAlmostEqual(self._tax(status, 200000), 16500.0, places=2)

"""Payroll calculation unit tests (pure helpers + tax sandbox)."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.limits import compute_limit
from payroll.methods.methods import compute_net_pay, get_total_days
from payroll.methods.payslip_calc import (
    calculate_based_on_basic_pay,
    calculate_based_on_net_pay,
    calculate_gross_pay,
    if_condition_on,
)
from payroll.methods.safe_tax_code import TaxCodeValidationError, validate_tax_code
from payroll.models.models import Payslip


class GetTotalDaysTests(TestCase):
    def test_inclusive_day_count(self):
        self.assertEqual(
            get_total_days(date(2023, 1, 1), date(2023, 1, 10)),
            10,
        )

    def test_same_day_is_one(self):
        self.assertEqual(get_total_days(date(2023, 5, 1), date(2023, 5, 1)), 1)


class ComputeLimitTests(TestCase):
    def test_no_max_limit_returns_amount(self):
        component = SimpleNamespace(has_max_limit=False, maximum_amount=100)
        self.assertEqual(compute_limit(component, 250.0, {}), 250.0)

    def test_max_limit_caps_amount(self):
        component = SimpleNamespace(has_max_limit=True, maximum_amount=100.0)
        self.assertEqual(compute_limit(component, 250.0, {}), 100.0)

    def test_under_limit_unchanged(self):
        component = SimpleNamespace(has_max_limit=True, maximum_amount=100.0)
        self.assertEqual(compute_limit(component, 40.0, {}), 40.0)


class RateBasedCalcTests(TestCase):
    def test_based_on_basic_pay(self):
        component = SimpleNamespace(rate=10, has_max_limit=False, maximum_amount=0)
        amount = calculate_based_on_basic_pay(
            component=component,
            basic_pay=10000.0,
            day_dict={},
        )
        self.assertEqual(amount, 1000.0)

    def test_based_on_basic_pay_respects_limit(self):
        component = SimpleNamespace(rate=50, has_max_limit=True, maximum_amount=200.0)
        amount = calculate_based_on_basic_pay(
            component=component,
            basic_pay=10000.0,
            day_dict={},
        )
        self.assertEqual(amount, 200.0)

    def test_based_on_net_pay(self):
        component = SimpleNamespace(rate=5, has_max_limit=False, maximum_amount=0)
        self.assertEqual(
            calculate_based_on_net_pay(component, 20000.0, {}),
            1000.0,
        )


class ComputeNetPayTests(TestCase):
    def test_passthrough(self):
        self.assertEqual(compute_net_pay(net_pay=1234.5), 1234.5)


class SafeTaxCodeTests(TestCase):
    def test_valid_code_accepted(self):
        code = (
            "def calculate_federal_tax(yearly_income):\n"
            "    return yearly_income * 0.1\n"
        )
        validate_tax_code(code)  # no raise

    def test_empty_rejected(self):
        with self.assertRaises(TaxCodeValidationError):
            validate_tax_code("")

    def test_import_rejected(self):
        code = (
            "import os\n" "def calculate_federal_tax(yearly_income):\n" "    return 0\n"
        )
        with self.assertRaises(TaxCodeValidationError):
            validate_tax_code(code)

    def test_missing_entry_point_rejected(self):
        code = "def other(yearly_income):\n    return 0\n"
        with self.assertRaises(TaxCodeValidationError):
            validate_tax_code(code)

    def test_format_string_dunder_bypass_rejected(self):
        # "{0.__class__}".format(x) walks attributes at runtime; the AST walk
        # only sees a string constant, so both the literal and the method
        # must be refused.
        for body in (
            'return "{0.__class__.__base__.__subclasses__}".format(yearly_income)',
            'return ("{0." + "__cl" + "ass__}").format(yearly_income)',
            'return "{x}".format_map({"x": yearly_income})',
        ):
            code = f"def calculate_federal_tax(yearly_income):\n    {body}\n"
            with self.assertRaises(TaxCodeValidationError, msg=body):
                validate_tax_code(code)


class PayslipValidationTests(TestCase):
    def setUp(self):
        company = make_company("Payroll Co")
        self.employee = make_employee(company=company, email="pay@test.horilla")

    def test_end_before_start_raises(self):
        today = date.today()
        slip = Payslip(
            employee_id=self.employee,
            start_date=today - timedelta(days=1),
            end_date=today - timedelta(days=5),
            pay_head_data={},
            basic_pay=0,
            gross_pay=0,
            deduction=0,
            net_pay=0,
        )
        with self.assertRaises(ValidationError):
            slip.clean()

    def test_future_end_date_raises(self):
        today = date.today()
        slip = Payslip(
            employee_id=self.employee,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5),
            pay_head_data={},
            basic_pay=0,
            gross_pay=0,
            deduction=0,
            net_pay=0,
        )
        with self.assertRaises(ValidationError):
            slip.clean()


class CalculateGrossPayTests(TestCase):
    @patch(
        "payroll.methods.payslip_calc.update_compensation_deduction",
        return_value={
            "compensation_amount": 11500.0,
            "deductions": [{"title": "comp"}],
        },
    )
    def test_gross_pay_uses_compensation_update(self, _mock):
        result = calculate_gross_pay(
            basic_pay=10000.0,
            total_allowance=2000.0,
            employee=object(),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        self.assertEqual(result["gross_pay"], 11500.0)
        self.assertEqual(result["basic_pay"], 10000.0)
        self.assertEqual(result["deductions"], [{"title": "comp"}])


class IfConditionOnTests(TestCase):
    @patch(
        "payroll.methods.payslip_calc.calculate_gross_pay",
        return_value={"gross_pay": 0},
    )
    def test_condition_fails_zeroes_amount(self, _mock):
        component = SimpleNamespace(
            if_choice="basic_pay",
            if_condition="gt",
            if_amount=20000,
            start_range=None,
            end_range=None,
        )
        amount = if_condition_on(
            component=component,
            basic_pay=10000.0,
            amount=500,
            total_allowance=0,
            employee=object(),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        self.assertEqual(amount, 0)

    @patch(
        "payroll.methods.payslip_calc.calculate_gross_pay",
        return_value={"gross_pay": 0},
    )
    def test_condition_passes_keeps_amount(self, _mock):
        component = SimpleNamespace(
            if_choice="basic_pay",
            if_condition="gt",
            if_amount=5000,
            start_range=None,
            end_range=None,
        )
        amount = if_condition_on(
            component=component,
            basic_pay=10000.0,
            amount=500,
            total_allowance=0,
            employee=object(),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        self.assertEqual(amount, 500.0)

    @patch(
        "payroll.methods.payslip_calc.calculate_gross_pay",
        return_value={"gross_pay": 0},
    )
    def test_range_outside_zeroes(self, _mock):
        component = SimpleNamespace(
            if_choice="basic_pay",
            if_condition="range",
            if_amount=0,
            start_range=8000,
            end_range=9000,
        )
        amount = if_condition_on(
            component=component,
            basic_pay=10000.0,
            amount=500,
            total_allowance=0,
            employee=object(),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        self.assertEqual(amount, 0)

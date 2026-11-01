"""Payroll calculation unit tests (pure helpers + tax sandbox)."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.safe_tax_code import TaxCodeValidationError, validate_tax_code
from payroll.models.models import Payslip


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

"""
The attendance a payslip was worked out from.

For an hourly contract the pay is rate x regular hours, and the payslip showed
neither the hours nor anything else to check the figure against — while
labelling the RATE as "Actual Basic Pay", so an employee paid 10/hour read
that their basic pay was 10.

Every figure here was already computed and carried in pay_head_data. Nothing
displayed it.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Contract
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

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

HOURLY = {
    "basic_pay": 2000.0,
    "loss_of_pay": 0,
    "paid_days": 10,
    "unpaid_days": 0,
    "regular_seconds": 72000,  # 20h
    "ot_regular_seconds": 7200,  # 2h
    "ot_week_off_seconds": 3600,  # 1h
    "ot_holiday_seconds": 0,
    "ot_seconds": 10800,  # 3h
}


class HourlyPayslipCarriesItsHoursTests(TestCase):
    def setUp(self):
        company = make_company("Hours Co")
        self.employee = make_employee(company=company, email="hours@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(
            self.employee, wage_type="hourly", wage=0, hourly_wage=100.0
        )

    def _run(self):
        """
        Patches hourly_computation, not compute_salary_on_period.

        The outer function assembles a good deal on top of the inner one --
        the contract, the contract wage, the month data -- and a mock of it
        has to reproduce all of that or the engine raises KeyError on whatever
        was forgotten. Mocking the attendance read instead leaves the real
        assembly running, which is also the part worth exercising.
        """
        from payroll.methods.payroll_run import payroll_calculation

        def months(wage, *_a, **_kw):
            return [
                {
                    "working_days_on_period": 22,
                    "working_days_on_month": 22,
                    "days": 30,
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                    "per_day_amount": float(wage or 0),
                }
            ]

        with patch(
            "payroll.methods.methods.hourly_computation", return_value=dict(HOURLY)
        ), patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            return payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

    def test_the_hours_reach_the_payslip_data(self):
        """
        Asserted on the engine's output, not the template: if these stop being
        carried, the template silently shows nothing rather than breaking.
        """
        data = self._run()
        for key in (
            "regular_hours_label",
            "ot_hours_label",
            "ot_regular_hours_label",
            "ot_week_off_hours_label",
        ):
            with self.subTest(key=key):
                self.assertIsNotNone(data.get(key), key)

    def test_the_labels_say_the_hours_worked(self):
        data = self._run()
        self.assertIn("20", data["regular_hours_label"])
        self.assertIn("3", data["ot_hours_label"])

    def test_the_rate_is_in_the_payslip_data_not_only_on_the_instance(self):
        """
        Both payslip templates print the hourly rate, and the PDF download
        path renders without setting `instance` — so an instance lookup would
        print nothing there and nowhere else, which is the kind of gap only
        the download reveals.
        """
        self.assertEqual(self._run()["contract_wage"], 100.0)

    def test_each_kind_of_overtime_is_reported_separately(self):
        """
        Each is paid by a different earning at a different rate, so one
        combined figure cannot be checked against the payslip lines.
        """
        data = self._run()
        self.assertIsNotNone(data["ot_regular_hours_label"])
        self.assertIsNotNone(data["ot_week_off_hours_label"])
        # And the total is the three added up, not a fourth measurement.
        self.assertIn("3", data["ot_hours_label"])

    def test_a_holiday_with_no_hours_is_not_reported(self):
        """
        Nothing worked on a holiday means no row, rather than a "0h 0m" line
        implying it was checked and came to nothing.
        """
        self.assertIsNone(self._run().get("ot_holiday_hours_label"))


class MonthlyPayslipHasNoHoursTests(TestCase):
    """A monthly contract has no hours to show, and must not invent any."""

    def setUp(self):
        company = make_company("Monthly Co")
        self.employee = make_employee(company=company, email="monthly@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def test_the_working_days_in_the_period_are_carried(self):
        """
        Paid days and loss-of-pay days are counts of something, and without
        the total they are counts of nothing: 21 loss-of-pay days reads very
        differently against 22 working days than against 30.
        """
        from payroll.methods.payroll_run import payroll_calculation

        def months(wage, *_a, **_kw):
            return [
                {
                    "working_days_on_period": 22,
                    "working_days_on_month": 22,
                    "days": 30,
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                    "per_day_amount": float(wage or 0) / 22,
                }
            ]

        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            data = payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

        self.assertEqual(data["working_days"], 22)

    def test_no_hour_labels_are_produced(self):
        from payroll.methods.payroll_run import payroll_calculation

        def months(wage, *_a, **_kw):
            return [
                {
                    "working_days_on_period": 22,
                    "working_days_on_month": 22,
                    "days": 30,
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                    "per_day_amount": float(wage or 0) / 22,
                }
            ]

        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            data = payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

        self.assertIsNone(data.get("regular_hours_label"))
        self.assertIsNone(data.get("ot_hours_label"))


class TheRenderedPayslipTests(TestCase):
    """
    Asserted against the template that actually renders.

    horilla_theme/templates/ shadows payroll/templates/ for this file, so
    editing the app copy changed nothing on screen. Rendering through the view
    is the only check that cannot be fooled by that.
    """

    def setUp(self):
        user = make_user("slipadmin", is_superuser=True)
        company = make_company("Slip Co")
        make_employee(company=company, email="slipadmin@test.horilla", user=user)
        self.client.force_login(user)

        from payroll.models.tax_models import PayrollSettings

        PayrollSettings.objects.create(currency_symbol="$", position="postfix")
        self.employee = make_employee(company=company, email="slip@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(
            self.employee, wage_type="hourly", wage=0, hourly_wage=100.0
        )

    def _payslip(self, **head):
        from payroll.models.models import Payslip

        data = {
            "paid_days": 10,
            "unpaid_days": 21,
            "total_calendar_days": 31,
            "basic_pay": 2000.0,
            "contract_wage": 100.0,
            "taxable_gross_pay": 2000.0,
            "net_pay": 2000.0,
            "allowances": [],
            "pretax_deductions": [],
            "post_tax_deductions": [],
            "tax_deductions": [],
            "net_deductions": [],
            "gross_pay": 2000.0,
            "total_deductions": 0.0,
            "regular_hours_label": "20h 0m",
            "ot_hours_label": "3h 0m",
            "ot_regular_hours_label": "2h 0m",
            "ot_week_off_hours_label": "1h 0m",
            "ot_holiday_hours_label": None,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        }
        data.update(head)
        return Payslip.objects.create(
            employee_id=self.employee,
            start_date="2026-08-01",
            end_date="2026-08-31",
            status="draft",
            basic_pay=2000.0,
            contract_wage=100.0,
            gross_pay=2000.0,
            deduction=0.0,
            net_pay=2000.0,
            pay_head_data=data,
        )

    def _body(self, payslip):
        from django.template.loader import render_to_string

        data = dict(payslip.pay_head_data)
        data["employee"] = payslip.employee_id
        data["instance"] = payslip
        return render_to_string("payroll/payslip/individual_payslip_summery.html", data)

    def test_the_hours_lead_an_hourly_payslip(self):
        body = self._body(self._payslip()).lower()
        for label in (
            "hourly rate",
            "regular hours",
            "regular ot",
            "week off ot",
            "holiday ot",
        ):
            with self.subTest(label=label):
                self.assertIn(label, body)
        for figure in ("20h 0m", "2h 0m", "1h 0m", "3h 0m"):
            with self.subTest(figure=figure):
                self.assertIn(figure, body)

    def test_days_and_basic_pay_are_not_shown_for_an_hourly_contract(self):
        """
        They belong to a monthly contract and mislead here: the pay is not a
        monthly figure divided by days, and nobody is "paid" for a day.
        """
        body = self._body(self._payslip()).lower()
        # Tag-boundary, not a bare substring: "unpaid days" (the LOP
        # popover's own label, present on every wage type) contains "paid
        # days" too, and a plain assertNotIn("paid days", ...) collided with
        # it -- passing only because this test had never been run as part
        # of the full suite before.
        self.assertNotIn(">paid days<", body)
        # Nor under any other name. hourly_computation returns loss_of_pay = 0
        # always -- an hour not worked is an hour not paid, not pay withheld --
        # so a days count here would imply a deduction that was never made.
        self.assertNotIn("days not worked", body)
        self.assertNotIn("loss of pay days", body)
        # Basic pay is still an EARNINGS line -- it is the strip it is off.
        strip = body.split("ps__ledger")[0]
        self.assertNotIn("basic pay", strip)

    def test_an_overtime_kind_that_came_to_nothing_still_has_a_row(self):
        """
        "No holiday overtime" is an answer; a missing row is not. The fixture
        has no holiday hours.
        """
        body = self._body(self._payslip()).lower()
        self.assertIn("holiday ot", body)

    def test_the_hours_are_not_shown_twice(self):
        """
        The strip replaced a separate Attendance panel that said the same four
        things, which invited the reader to check one against the other.
        """
        body = self._body(self._payslip())
        self.assertEqual(body.count("20h 0m"), 1)

    def test_the_rate_is_not_called_basic_pay(self):
        """An employee paid 100/hour does not have a basic pay of 100."""
        # Case-insensitive: the labels are sentence case in the markup and
        # uppercased by CSS, so asserting the rendered casing would break on
        # a styling change that means nothing.
        body = self._body(self._payslip()).lower()
        self.assertIn("hourly rate", body)
        self.assertNotIn("actual basic pay", body)

    def test_a_monthly_payslip_names_the_wage_and_its_lop_days(self):
        """The hourly wording must not leak onto a monthly payslip."""
        monthly = self._payslip(
            regular_hours_label=None,
            ot_hours_label=None,
            ot_regular_hours_label=None,
            ot_week_off_hours_label=None,
        )
        body = self._body(monthly).lower()

        self.assertIn("contract wage", body)
        self.assertIn("loss of pay days", body)
        # The calendar-day total is shown against paid days rather than as a
        # figure of its own -- it only means anything as the thing paid days
        # are counted against.
        self.assertNotIn("working days", body)
        self.assertIn("of 31", body)
        self.assertNotIn("days not worked", body)
        self.assertNotIn("hourly rate", body)
        self.assertNotIn("regular ot", body)
        self.assertIn("paid days", body)


class CurrencyWithoutSettingsTests(TestCase):
    """
    The payslip on a system where payroll settings were never saved.

    currency_symbol_position guarded for a missing PayrollSettings row when
    reading the symbol and then did not when reading the position, so every
    payslip page raised AttributeError on a fresh install or a new company.
    """

    def test_the_filter_survives_no_settings_row(self):
        from base.templatetags.horillafilters import currency_symbol_position
        from payroll.models.tax_models import PayrollSettings

        PayrollSettings.objects.all().delete()
        self.assertEqual(currency_symbol_position("100.00"), "100.00 $")

    def test_it_uses_the_row_when_there_is_one(self):
        from base.templatetags.horillafilters import currency_symbol_position
        from payroll.models.tax_models import PayrollSettings

        PayrollSettings.objects.all().delete()
        PayrollSettings.objects.create(currency_symbol="€", position="prefix")
        self.assertEqual(currency_symbol_position("100.00"), "€ 100.00")

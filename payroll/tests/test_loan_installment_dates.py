"""Loan installment dates: a start on the 30th or 31st keeps its day where the month has it (#1317)."""

from datetime import date

from django.test import SimpleTestCase

from base.methods import get_nth_month_same_date
from payroll.models.models import LoanAccount


def schedule(start, installments):
    loan = LoanAccount(
        loan_amount=1200, installments=installments, installment_start_date=start
    )
    return list(loan.get_installments())


class LoanInstallmentDatesTests(SimpleTestCase):
    def test_start_on_the_31st_returns_to_the_31st(self):
        self.assertEqual(
            schedule(date(2027, 1, 31), 4),
            ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"],
        )

    def test_start_on_the_30th_does_not_drift_to_the_28th(self):
        self.assertEqual(
            schedule(date(2027, 1, 30), 4),
            ["2027-01-30", "2027-02-28", "2027-03-30", "2027-04-30"],
        )

    def test_leap_year_february_has_a_29th(self):
        self.assertEqual(
            schedule(date(2028, 1, 31), 3),
            ["2028-01-31", "2028-02-29", "2028-03-31"],
        )

    def test_schedule_crosses_the_year_end(self):
        self.assertEqual(
            schedule(date(2026, 10, 31), 4),
            ["2026-10-31", "2026-11-30", "2026-12-31", "2027-01-31"],
        )

    def test_nth_month_is_counted_from_the_start_date_not_the_previous_month(self):
        start = date(2027, 1, 31)
        self.assertEqual(get_nth_month_same_date(start, 1), date(2027, 2, 28))
        self.assertEqual(get_nth_month_same_date(start, 2), date(2027, 3, 31))

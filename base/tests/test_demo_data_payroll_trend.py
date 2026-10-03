"""_target_periods: which month(s) get a demo payslip, and their real bounds."""

from datetime import date

from django.test import SimpleTestCase, TestCase

from base.demo_data.modules.payroll_trend import (
    _target_periods,
    backfill_payroll_coverage,
)
from horilla.testkit import make_company, make_employee
from payroll.models.models import Contract, Payslip
from payroll.tests.factories_payroll import make_active_contract


class TargetPeriodsTests(SimpleTestCase):
    def test_last_day_of_month_generates_only_the_current_month(self):
        # September has 30 days.
        periods = _target_periods(date(2026, 9, 30))
        self.assertEqual(len(periods), 1)
        offset, start, end = periods[0]
        self.assertEqual(offset, 0)
        self.assertEqual(start, date(2026, 9, 1))
        self.assertEqual(end, date(2026, 9, 30))

    def test_mid_month_skips_the_current_month_for_the_two_before_it(self):
        periods = _target_periods(date(2026, 9, 15))
        offsets = [p[0] for p in periods]
        self.assertEqual(offsets, [1, 2])
        # M-1: August (31 days), M-2: July (31 days) -- neither is September.
        self.assertEqual(periods[0][1:], (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(periods[1][1:], (date(2026, 7, 1), date(2026, 7, 31)))

    def test_period_end_is_the_real_last_day_not_the_28th(self):
        # 30-day month.
        periods = _target_periods(date(2026, 5, 15))
        self.assertEqual(periods[0][1:], (date(2026, 4, 1), date(2026, 4, 30)))

    def test_crosses_a_year_boundary(self):
        periods = _target_periods(date(2026, 1, 15))
        offsets_and_months = [(p[0], p[1].year, p[1].month) for p in periods]
        self.assertEqual(offsets_and_months, [(1, 2025, 12), (2, 2025, 11)])

    def test_last_day_of_february_non_leap_year(self):
        periods = _target_periods(date(2026, 2, 28))
        self.assertEqual(periods[0][1:], (date(2026, 2, 1), date(2026, 2, 28)))

    def test_last_day_of_february_leap_year(self):
        periods = _target_periods(date(2028, 2, 29))
        self.assertEqual(periods[0][1:], (date(2028, 2, 1), date(2028, 2, 29)))

    def test_28th_of_a_longer_month_is_not_treated_as_month_end(self):
        # The bug this whole change replaces: the 28th used to be treated as
        # if it always closed the month, which is wrong for anything but Feb.
        periods = _target_periods(date(2026, 9, 28))
        self.assertEqual([p[0] for p in periods], [1, 2])


class BackfillPayrollCoverageTests(TestCase):
    """The end-to-end path: only 1 or 2 payslips per new employee, never 6."""

    def setUp(self):
        self.company = make_company("Trend Co")
        self.employee = make_employee(company=self.company, email="trend@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def test_mid_month_backfills_exactly_two_payslips(self):
        created = backfill_payroll_coverage(today=date(2026, 9, 15))
        self.assertEqual(created, 2)
        self.assertEqual(Payslip.objects.filter(employee_id=self.employee).count(), 2)

    def test_month_end_backfills_exactly_one_payslip(self):
        created = backfill_payroll_coverage(today=date(2026, 9, 30))
        self.assertEqual(created, 1)
        payslip = Payslip.objects.get(employee_id=self.employee)
        self.assertEqual(payslip.start_date, date(2026, 9, 1))
        self.assertEqual(payslip.end_date, date(2026, 9, 30))

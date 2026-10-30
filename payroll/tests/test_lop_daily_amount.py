"""
What one unpaid day costs.

Two branches of compute_salary_on_period work loss of pay out, and they
disagreed. The monthly branch asked get_daily_salary, which reads the
contract's "Daily Leave Amount From" and "Divided By". The attendance-summary
branch — the one generate_payslip actually takes — worked it out itself as
`wage / total_days`, where total_days counts every day in the month including
week offs and holidays.

So a 25,000 wage over a 31 day August priced an unpaid day at 806.45 on one
path and 1,086.96 on the other, and a contract set to divide by working days
was honoured on one and ignored on the other. 21 unpaid days came to
16,935.48 instead of 22,826.09 — a difference of nearly six thousand on one
payslip.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.methods import compute_salary_on_period, get_daily_salary
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract

AUGUST = {
    "present": 10,
    "paid_leave": 0,
    "unpaid_leave": 21,
    "absent": 0,
    "week_off": 0,
    "holiday": 0,
    "total_working": 23,
}


class DailyAmountFollowsTheContractTests(TestCase):
    def setUp(self):
        company = make_company("LOP Co")
        self.employee = make_employee(company=company, email="lop@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _contract(self, **kwargs):
        return make_active_contract(self.employee, wage=25000.0, **kwargs)

    def test_working_days_and_calendar_days_give_different_answers(self):
        """
        The whole reason the setting exists: August 2026 has 31 calendar days
        and 23 working days, so the two readings are far apart.

        get_working_days is patched because it reads the company's configured
        working days, and a bare test company has none — every day counts,
        and the two divisors would agree for the wrong reason.
        """
        working = self._contract(daily_leave_amount_divisor="working_days")

        with patch(
            "payroll.methods.methods.get_working_days",
            return_value={"total_working_days": 23},
        ):
            by_working = get_daily_salary(25000.0, date(2026, 8, 1), working)[
                "day_wage"
            ]

            working.daily_leave_amount_divisor = "calendar_days"
            working.save()
            by_calendar = get_daily_salary(25000.0, date(2026, 8, 1), working)[
                "day_wage"
            ]

        self.assertAlmostEqual(by_working, 25000.0 / 23, places=4)
        self.assertAlmostEqual(by_calendar, 25000.0 / 31, places=4)

    def test_the_monthly_ctc_base_is_used_when_chosen(self):
        contract = self._contract(
            monthly_ctc=40000.0,
            daily_leave_amount_base="monthly_ctc",
            daily_leave_amount_divisor="calendar_days",
        )
        self.assertAlmostEqual(
            get_daily_salary(25000.0, date(2026, 8, 1), contract)["day_wage"],
            40000.0 / 31,
            places=4,
        )

    def test_a_missing_ctc_falls_back_to_the_wage(self):
        """Otherwise choosing CTC on a contract without one makes days free."""
        contract = self._contract(
            monthly_ctc=None,
            daily_leave_amount_base="monthly_ctc",
            daily_leave_amount_divisor="calendar_days",
        )
        self.assertAlmostEqual(
            get_daily_salary(25000.0, date(2026, 8, 1), contract)["day_wage"],
            25000.0 / 31,
            places=4,
        )


class AttendanceBranchUsesTheSameRuleTests(TestCase):
    """
    The branch generate_payslip takes. It is the one that was wrong.
    """

    def setUp(self):
        company = make_company("LOP Branch Co")
        self.employee = make_employee(company=company, email="lopb@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _run(self, **contract_kwargs):
        make_active_contract(self.employee, wage=25000.0, **contract_kwargs)

        def months(wage, *_a, **_kw):
            return [
                {
                    "working_days_on_period": 23,
                    "working_days_on_month": 23,
                    "days": 31,
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-31",
                    "per_day_amount": float(wage or 0) / 23,
                }
            ]

        with patch(
            "payroll.methods.methods.get_working_days",
            return_value={"total_working_days": 23},
        ), patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_leaves",
            return_value={
                "paid_leave": 0,
                "unpaid_leaves": 21,
                "partial_pay_days": 0,
                "total_leaves": 21,
                "paid_leave_dates": [],
                "unpaid_leave_dates": [],
                "custom_leave_dates": [],
                "custom_leave_breakdown": [],
                "leave_dates": [],
            },
        ):
            return compute_salary_on_period(
                self.employee,
                date(2026, 8, 1),
                date(2026, 8, 31),
                month_summary=dict(AUGUST),
            )

    def test_calendar_days_prices_a_day_against_the_whole_month(self):
        data = self._run(daily_leave_amount_divisor="calendar_days")
        self.assertAlmostEqual(data["loss_of_pay"], 25000.0 / 31 * 21, places=2)

    def test_working_days_prices_it_against_the_working_days(self):
        """
        This is the case that was broken: the contract said working days and
        the branch divided by 31 anyway.
        """
        data = self._run(daily_leave_amount_divisor="working_days")
        self.assertAlmostEqual(data["loss_of_pay"], 25000.0 / 23 * 21, places=2)
        # And emphatically not the old figure.
        self.assertNotAlmostEqual(data["loss_of_pay"], 25000.0 / 31 * 21, places=2)

    def test_a_flat_per_leave_amount_is_honoured_here_too(self):
        """
        The branch ignored "calculate daily leave amount" entirely and always
        worked a daily figure out.
        """
        data = self._run(
            calculate_daily_leave_amount=False,
            deduction_for_one_leave_amount=100.0,
        )
        self.assertAlmostEqual(data["loss_of_pay"], 21 * 100.0, places=2)

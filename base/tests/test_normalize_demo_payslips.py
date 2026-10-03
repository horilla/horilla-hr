"""normalize_demo_payslips: recompute through the real engine, not just re-date.

Covers the two failure modes a plain date-shift left in place: a payslip
whose numbers were whatever the fixture author baked in years ago (unrelated
to the employee's actual attendance), and a payslip for an employee who no
longer has an active contract to compute one against at all.
"""

import calendar
import datetime as dt
from datetime import date, datetime, timedelta

from django.test import TestCase

from attendance.models import Attendance
from base.views import (
    DEMO_PAYROLL_GROUP_PREFIX,
    DEMO_PAYROLL_RENAMED_PREFIX,
    normalize_demo_payslips,
)
from horilla.testkit import make_company, make_employee
from payroll.models.models import Contract, Payslip
from payroll.tests.factories_payroll import make_active_contract


def _month_bounds(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _seed_full_attendance(employee, start, end):
    """
    A full day of work on every weekday in [start, end] -- without this, the
    real attendance summary correctly reads as 100% absent (no clock-in
    anywhere), which is a legitimate answer but not one that tells this test
    apart from a broken computation returning a flat zero.
    """
    day = start
    while day <= end:
        if day.weekday() < 5:
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=day,
                attendance_clock_in=dt.time(9, 0),
                attendance_clock_out=dt.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )
        day += timedelta(days=1)


class NormalizeDemoPayslipsTests(TestCase):
    def setUp(self):
        self.company = make_company("Normalize Co")
        self.employee = make_employee(
            company=self.company, email="normalize@test.horilla"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = make_active_contract(self.employee, wage=30000.0)

        today = datetime.today().date()
        self.offset = 1
        year, month = today.year, today.month - self.offset
        if month < 1:
            month += 12
            year -= 1
        self.expected_start, self.expected_end = _month_bounds(year, month)
        _seed_full_attendance(self.employee, self.expected_start, self.expected_end)

    def _stale_payslip(self, **overrides):
        defaults = dict(
            employee_id=self.employee,
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 28),
            status="paid",
            contract_wage=1.0,
            basic_pay=1.0,
            gross_pay=1.0,
            deduction=0.0,
            net_pay=1.0,
            pay_head_data={
                "paid_days": 999,
                "unpaid_days": 999,
                "start_date": "2020-01-01",
                "end_date": "2020-01-28",
            },
            group_name=f"{DEMO_PAYROLL_GROUP_PREFIX}{self.offset}",
        )
        defaults.update(overrides)
        return Payslip.objects.create(**defaults)

    def test_recomputes_real_figures_not_just_dates(self):
        """
        The bug report this exists for: "22 of 30 paid days, 0 loss of pay"
        that had nothing to do with the employee's real attendance, because
        only start_date/end_date were ever touched.
        """
        self._stale_payslip()
        normalize_demo_payslips()

        payslip = Payslip.objects.get(employee_id=self.employee)
        self.assertEqual(payslip.start_date, self.expected_start)
        self.assertEqual(payslip.end_date, self.expected_end)
        # A real computation against a 30000 wage does not land on 1.0.
        self.assertGreater(payslip.basic_pay, 1000)
        self.assertNotEqual(payslip.pay_head_data.get("paid_days"), 999)
        self.assertNotEqual(payslip.pay_head_data.get("unpaid_days"), 999)

    def test_deletes_payslips_for_employees_without_an_active_contract(self):
        """A payslip cannot be recomputed for someone with no active contract
        to read a wage from -- it should not keep existing under a fake date
        either."""
        payslip = self._stale_payslip()
        Contract.objects.filter(employee_id=self.employee).delete()

        normalize_demo_payslips()

        self.assertFalse(Payslip.objects.filter(pk=payslip.pk).exists())

    def test_renames_group_to_readable_label(self):
        self._stale_payslip()
        normalize_demo_payslips()

        payslip = Payslip.objects.get(employee_id=self.employee)
        self.assertTrue(payslip.group_name.startswith(DEMO_PAYROLL_RENAMED_PREFIX))
        self.assertNotIn("M-", payslip.group_name)

    def test_already_renamed_rows_are_still_recognized_on_a_later_run(self):
        """The "M-<n>" tag is gone after the first rename; the offset must be
        re-derivable from start_date alone, or a payslip only ever gets
        recomputed once and then drifts stale forever."""
        self._stale_payslip(
            start_date=self.expected_start,
            end_date=self.expected_end,
            group_name=f"{DEMO_PAYROLL_RENAMED_PREFIX}Some Month",
        )
        normalize_demo_payslips()

        payslip = Payslip.objects.get(employee_id=self.employee)
        self.assertEqual(payslip.start_date, self.expected_start)
        self.assertEqual(payslip.end_date, self.expected_end)
        self.assertGreater(payslip.basic_pay, 1000)

    def test_current_month_payslip_cannot_stay_paid(self):
        """M-0 only exists when _target_periods judged the current month
        already closed, but a demo row could still ship "paid" for it from
        an older run -- the engine cannot have produced that itself yet."""
        today = datetime.today().date()
        start, end = _month_bounds(today.year, today.month)
        self._stale_payslip(
            start_date=start,
            end_date=end,
            status="paid",
            group_name=f"{DEMO_PAYROLL_GROUP_PREFIX}0",
        )
        normalize_demo_payslips()

        payslip = Payslip.objects.get(employee_id=self.employee)
        self.assertEqual(payslip.status, "review_ongoing")

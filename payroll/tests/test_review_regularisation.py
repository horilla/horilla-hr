"""
Fixing attendance from the payroll run review.

An unresolved conflict is the one thing that blocks a run, and the fix for it
lived on another screen. The calendar and its conflict resolution are hosted on
the review itself, so these cover what the review works out for its rows: the
period each row opens, the blocked and low-paid counts and that a fresh request
recomputes them.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract
from payroll.views.batch_views import SESSION_KEY

START = date(2026, 4, 1)
END = date(2026, 4, 30)

CLEAN = {
    "present": 22,
    "paid_leave": 0,
    "unpaid_leave": 0,
    "absent": 0,
    "week_off": 8,
    "holiday": 0,
    "total_working": 22,
    "unresolved_conflicts": 0,
    "overtime_label": "0h 00m",
}


class ReviewPageTests(TestCase):
    def setUp(self):
        self.user = make_user("regadmin", is_superuser=True)
        self.company = make_company("Reg Co")
        make_employee(
            company=self.company, email="regadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.employee = make_employee(
            company=self.company, email="reg@test.horilla", first_name="Reg"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

        session = self.client.session
        session[SESSION_KEY] = {
            "batch_name": "April",
            "period_start": START.isoformat(),
            "period_end": END.isoformat(),
            "employee_ids": [self.employee.pk],
        }
        session.save()

    def review(self, **overrides):
        summary = dict(CLEAN)
        summary.update(overrides)
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value={self.employee.pk: summary},
        ):
            return self.client.get(reverse("payroll-batch-review"))

    def test_each_row_can_open_that_employees_period(self):
        """
        The employee and the exact period being paid -- not today's month.
        Regularising the wrong month would leave the run blocked and look like
        the fix did nothing.
        """
        response = self.review()
        body = response.content.decode()

        self.assertIn(f"employee_id={self.employee.pk}", body)
        self.assertIn("from_date=2026-04-01", body)
        self.assertIn("to_date=2026-04-30", body)

    def test_few_paid_days_is_counted_and_marked(self):
        """
        Not a blocker -- a mid-month joiner or a long sickness legitimately has
        few paid days -- but on a list of two hundred it is the handful worth
        checking before the payslips exist rather than after.
        """
        response = self.review(paid_days=4)

        self.assertEqual(response.context["low_paid_count"], 1)
        self.assertContains(response, "pb__low")

    def test_a_full_month_is_not_flagged(self):
        response = self.review(paid_days=30)
        self.assertEqual(response.context["low_paid_count"], 0)

    def test_a_blocked_row_is_not_double_counted(self):
        """
        It is already reported as blocked; counting it twice would make the
        two figures overlap and neither of them mean anything on its own.
        """
        response = self.review(paid_days=0, unresolved_conflicts=1)

        self.assertEqual(response.context["blocked_count"], 1)
        self.assertEqual(response.context["low_paid_count"], 0)

    def test_a_fresh_review_is_recomputed_after_fixing(self):
        """A saved calendar or contract reloads the review; there is no Re-check button."""
        self.assertEqual(
            self.review(unresolved_conflicts=1).context["blocked_count"], 1
        )

        # A fresh request is genuinely recomputed: with the conflict gone nobody is blocked.
        self.assertEqual(self.review().context["blocked_count"], 0)

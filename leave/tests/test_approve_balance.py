"""Tests for leave approve balance deduction and sufficiency gate."""

from datetime import date, timedelta

from django.test import TestCase


class LeaveRequestApproveBalanceTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Approve Bal Co")
        self.employee = make_employee(company=company, email="approvebal@test.horilla")
        self.leave_type = LeaveType.objects.create(
            name="Approve Balance Leave",
            total_days=20,
        )
        self.AvailableLeave = AvailableLeave

    def _request(self, days):
        from leave.models import LeaveRequest

        today = date.today()
        return LeaveRequest(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            start_date=today + timedelta(days=3),
            end_date=today + timedelta(days=3),
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            requested_days=days,
            description="approve balance test",
            status="requested",
            approved_available_days=0,
            approved_carryforward_days=0,
        )

    def test_has_sufficient_leave_balance_gate(self):
        from leave.services import has_sufficient_leave_balance

        avail = self.AvailableLeave(
            available_days=2,
            carryforward_days=1,
        )
        self.assertTrue(has_sufficient_leave_balance(avail, 3))
        self.assertFalse(has_sufficient_leave_balance(avail, 4))

    def test_approve_reduces_available_days(self):
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )
        req = self._request(3)
        req.no_approval()
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 2)
        self.assertEqual(req.approved_available_days, 3)
        self.assertEqual(req.status, "approved")

    def test_approve_dips_into_carryforward(self):
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            available_days=1,
            carryforward_days=4,
            total_leave_days=5,
        )
        req = self._request(3)
        req.no_approval()
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 0)
        self.assertEqual(avail.carryforward_days, 2)
        self.assertEqual(req.approved_available_days, 1)
        self.assertEqual(req.approved_carryforward_days, 2)
        self.assertEqual(req.status, "approved")

"""Forecasted leave requests: the paths around the main flow (API, bulk, multi-level, expiry, half days)."""

import json
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from horilla.testkit import make_employee, make_user
from leave import forecast
from leave.models import (
    AvailableLeave,
    LeaveRequest,
    LeaveRequestConditionApproval,
    LeaveType,
)
from leave.services import charge_leave_request
from leave.tests.test_forecast_request import (
    NEXT_RESET,
    RESET,
    TODAY,
    ForecastBase,
    first_of_next_month,
)

APPROVE = "/api/v1/leave/approve/{}/"
BULK = "/api/v1/leave/request-bulk-action/"
CREATE = "/api/v1/leave/request/"


class ApiTests(ForecastBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.admin_user)

    def test_the_api_approves_a_leave_after_the_reset_like_the_web(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        response = self.api.put(
            APPROVE.format(leave.pk), {"available_leave": avail.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual((avail.available_days, avail.reset_date), (7, NEXT_RESET))

    def test_the_api_refuses_what_neither_the_balance_nor_the_forecast_covers(self):
        avail = self.balance(available=0)
        leave = self.leave(
            RESET + timedelta(days=1), RESET + timedelta(days=15)
        )  # 15 days, 10 a cycle
        response = self.api.put(
            APPROVE.format(leave.pk), {"available_leave": avail.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertEqual((avail.available_days, avail.reset_date), (0, RESET))

    def test_the_api_bulk_approve_takes_what_fits_and_leaves_the_rest(self):
        avail = self.balance(available=0)
        fits = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        too_big = self.leave(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=15)
        )
        response = self.api.put(
            BULK, {"leave_request_id": [fits.pk, too_big.pk]}, format="multipart"
        )
        self.assertEqual(response.status_code, 200, response.content)
        fits.refresh_from_db()
        too_big.refresh_from_db()
        self.assertEqual((fits.status, too_big.status), ("approved", "requested"))

    def test_creating_through_the_api_follows_the_forecast(self):
        self.balance(available=0)
        day = (RESET + timedelta(days=2)).isoformat()
        response = self.api.post(
            CREATE,
            {
                "employee_id": self.employee.pk,
                "leave_type_id": self.leave_type.pk,
                "start_date": day,
                "end_date": day,
                "description": "api forecast",
            },
            format="json",
        )
        self.assertIn(response.status_code, (200, 201), response.content)


class MultiLevelApprovalTests(ForecastBase):
    """A leave approved by several people only changes the balance when the last one approves."""

    def setUp(self):
        super().setUp()
        company = self.employee.employee_work_info.company_id
        self.first_user = make_user("forecast_first", password="secret123")
        self.first = make_employee(
            company=company, email="forecast_first@test.horilla", user=self.first_user
        )
        self.last_user = make_user("forecast_last", password="secret123")
        self.last = make_employee(
            company=company, email="forecast_last@test.horilla", user=self.last_user
        )
        permission = Permission.objects.get(codename="change_leaverequest")
        self.first_user.user_permissions.add(permission)
        self.last_user.user_permissions.add(permission)

    def approve(self, user, leave):
        self.client.force_login(user)
        return self.client.get(
            reverse("request-approve", args=[leave.pk]),
            {"confirm": 1},
            HTTP_HX_REQUEST="true",
        )

    def test_only_the_last_approval_brings_the_balance_forward(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        LeaveRequestConditionApproval.objects.create(
            manager_id=self.first, sequence=1, leave_request_id=leave
        )
        LeaveRequestConditionApproval.objects.create(
            manager_id=self.last, sequence=2, leave_request_id=leave
        )

        self.approve(self.first_user, leave)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertEqual(
            (avail.available_days, avail.reset_date), (0, RESET)
        )  # nothing written yet
        self.assertFalse([r for r in self.reasons(avail) if r and "provided" in r])

        self.approve(self.last_user, leave)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual((avail.available_days, avail.reset_date), (7, NEXT_RESET))


class WebEdgeCaseTests(ForecastBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def test_approving_twice_does_not_bring_the_balance_forward_twice(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        url = reverse("request-approve", args=[leave.pk])
        self.client.get(url, {"confirm": 1}, HTTP_HX_REQUEST="true")
        self.client.get(url, {"confirm": 1}, HTTP_HX_REQUEST="true")
        avail.refresh_from_db()
        self.assertEqual((avail.available_days, avail.reset_date), (7, NEXT_RESET))
        self.assertEqual(
            len(
                [
                    r
                    for r in self.reasons(avail)
                    if r and r.startswith("Forecasted leave taken")
                ]
            ),
            1,
        )

    def test_bulk_approve_takes_what_fits_and_leaves_the_rest(self):
        avail = self.balance(available=0)
        fits = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        too_big = self.leave(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=15)
        )
        self.client.post(
            reverse("leave-requests-bulk-approve"),
            {"ids": json.dumps([fits.pk, too_big.pk])},
        )
        fits.refresh_from_db()
        too_big.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual((fits.status, too_big.status), ("approved", "requested"))
        self.assertEqual(avail.available_days, 7)

    def test_half_days_are_brought_forward_as_half_days(self):
        avail = self.balance(available=0)
        day = RESET + timedelta(days=1)
        leave = self.leave(
            day, day, start_date_breakdown="first_half", end_date_breakdown="first_half"
        )
        self.assertEqual(leave.requested_days, 0.5)
        self.client.get(
            reverse("request-approve", args=[leave.pk]),
            {"confirm": 1},
            HTTP_HX_REQUEST="true",
        )
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 9.5)

    def test_a_balance_with_no_reset_date_is_never_brought_forward(self):
        avail = self.balance(available=0)
        AvailableLeave.objects.filter(pk=avail.pk).update(reset_date=None)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        response = self.client.get(
            reverse("request-approve", args=[leave.pk]), HTTP_HX_REQUEST="true"
        )
        leave.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertIn("leaveBalanceShort", json.loads(response["HX-Trigger"]))


class YearlyResetTests(ForecastBase):
    def test_a_yearly_type_is_brought_forward_to_its_yearly_reset(self):
        self.leave_type.reset_based = "yearly"
        self.leave_type.reset_month = str(RESET.month)
        self.leave_type.reset_day = "1"
        self.leave_type.save()
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual(avail.available_days, 7)
        self.assertEqual(avail.reset_date, RESET.replace(year=RESET.year + 1))


class CarryforwardExpiryTests(ForecastBase):
    carryforward_type = "carryforward expire"
    carryforward_max = 5

    def test_a_carryforward_that_expires_on_the_way_is_provided_too(self):
        self.leave_type.carryforward_expire_in = 1
        self.leave_type.carryforward_expire_period = "month"
        self.leave_type.save()
        avail = self.balance(available=1, carryforward=2)
        expiry = RESET - timedelta(days=1)
        AvailableLeave.objects.filter(pk=avail.pk).update(expired_date=expiry)
        avail.refresh_from_db()
        leave = self.leave(
            RESET + timedelta(days=1), RESET + timedelta(days=4)
        )  # 4 days, 3 held now
        result = forecast.check(avail, leave.end_date, 4)
        self.assertEqual(result.kind, forecast.OK_FORECAST)
        # The expiry (the day before the reset) happens first, then the reset on top of it.
        self.assertEqual(
            [step["kind"] for step in result.balance.steps], ["expiry", "reset"]
        )
        charge_leave_request(leave, avail, result=result)
        avail.save()
        avail.refresh_from_db()
        reasons = self.reasons(avail)
        self.assertIn(f"Leave reset provided: {RESET.isoformat()}", reasons)
        self.assertIn(f"Carryforward expired provided: {expiry.isoformat()}", reasons)
        self.assertEqual(
            (avail.available_days, avail.carryforward_days), (6, 5)
        )  # 10 and 5 carried, less 4
        self.assertGreater(avail.expired_date, expiry)

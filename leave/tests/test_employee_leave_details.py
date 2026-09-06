"""Tests for the employee-leave-details balance endpoint.

The view adds a forecast contribution to the current balance when a date is
supplied. That call used the no-argument `forcasted_leaves()` signature,
which had been shadowed by a two-argument redefinition further down
leave/models.py, so it raised TypeError -- swallowed by a bare `except` and
leaving the forecast silently out of the reported balance.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.models import AvailableLeave, LeaveType


class EmployeeLeaveDetailsForecastTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Forecast Balance Co")
        cls.user = make_user("forecast-balance")
        cls.employee = make_employee(
            company=company,
            email="forecast-balance@test.horilla",
            user=cls.user,
        )
        # reset_based monthly with a reset already behind us, so the
        # forecast for a future date is a non-zero number.
        cls.leave_type = LeaveType.objects.create(
            name="Casual Forecast Balance",
            total_days=12,
            reset=True,
            reset_based="monthly",
            reset_month="1",
            reset_day="1",
            carryforward_type="carryforward",
            carryforward_max=5,
        )
        cls.available = AvailableLeave.objects.create(
            employee_id=cls.employee,
            leave_type_id=cls.leave_type,
            available_days=4,
            carryforward_days=0,
        )

    def test_balance_includes_the_forecast_for_a_future_date(self):
        """With a date supplied the response must exceed available_days.

        Before the fix the forecast call raised TypeError inside a bare
        except, so the response was exactly available_days and the forecast
        contributed nothing.
        """
        self.client.force_login(self.user)
        future = date.today() + timedelta(days=60)

        response = self.client.post(
            reverse("employee-leave-details"),
            {
                "employee_id": str(self.employee.pk),
                "leave_type": str(self.leave_type.pk),
                "date": future.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(
            payload["leave_count"],
            self.available.available_days,
            "the forecast contributed nothing to the reported balance",
        )

"""Tests for a carryforward leave type saved without a carryforward maximum."""

import math
from datetime import date

from django.test import TestCase


class CarryforwardNoMaxTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Carry No Max Co")
        self.employee = make_employee(company=company, email="nomax@test.horilla")
        self.LeaveType = LeaveType
        self.AvailableLeave = AvailableLeave

    def _leave_type(self, **kwargs):
        return self.LeaveType.objects.create(
            name="Carry No Max",
            total_days=10,
            reset=True,
            reset_based="monthly",
            reset_day="1",
            carryforward_type="carryforward",
            **kwargs,
        )

    def test_saves_and_is_audited_without_a_maximum(self):
        from auditlog.models import LogEntry

        lt = self._leave_type()
        lt.refresh_from_db()
        self.assertIsNone(lt.carryforward_max)

        entry = LogEntry.objects.get_for_object(lt).latest("timestamp")
        self.assertIsNone(entry.serialized_data["fields"]["carryforward_max"])

    def test_form_with_blank_maximum_saves(self):
        from leave.forms import LeaveTypeForm

        form = LeaveTypeForm(
            data={
                "name": "Carry No Max Form",
                "icon_color": "#000000",
                "payment_type": "paid",
                "payment": "paid",
                "count": "10",
                "period_in": "day",
                "total_days": "10",
                "limit_leave": "on",
                "reset": "on",
                "reset_based": "monthly",
                "reset_day": "1",
                "carryforward_type": "carryforward",
                "carryforward_max": "",
                "carryforward_expiry_method": "first_expiry_date",
                "require_approval": "yes",
                "require_attachment": "no",
                "exclude_company_leave": "no",
                "exclude_holiday": "no",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        lt = form.save()
        lt.refresh_from_db()
        self.assertIsNone(lt.carryforward_max)

    def test_legacy_infinity_is_stored_as_null_on_next_save(self):
        lt = self._leave_type(carryforward_max=5)
        # Rows saved before this fix hold infinity for "no maximum".
        self.LeaveType.objects.filter(pk=lt.pk).update(carryforward_max=math.inf)
        lt.refresh_from_db()
        self.assertEqual(lt.carryforward_max, math.inf)

        # An edit is what writes an audit log entry for the leave type.
        lt.name = "Carry No Max Renamed"
        lt.save()
        lt.refresh_from_db()
        self.assertIsNone(lt.carryforward_max)

    def test_reset_carries_the_whole_balance_forward(self):
        lt = self._leave_type()
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=7,
            carryforward_days=0,
            total_leave_days=7,
            reset_date=date.today(),
        )

        forecast = avail.forecast_next_reset()
        self.assertEqual(forecast["balance"], 17)

        avail.update_carryforward()
        self.assertEqual(avail.carryforward_days, 7)
        self.assertEqual(avail.available_days, 10)

    def test_maximum_still_caps_the_carryforward(self):
        lt = self._leave_type(carryforward_max=3)
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=7,
            carryforward_days=0,
            total_leave_days=7,
        )
        avail.update_carryforward()
        self.assertEqual(avail.carryforward_days, 3)

    def test_request_forecast_carries_the_whole_balance_forward(self):
        from leave import forecast

        self.assertEqual(forecast.after_reset(self._leave_type(), 7, 0), (10.0, 7.0))
        lt = self._leave_type(carryforward_max=3)
        self.assertEqual(forecast.after_reset(lt, 7, 0), (10.0, 3.0))

    def test_reset_policy_says_no_limit(self):
        from leave.views import _reset_policy

        self.assertIn("Carry Forward, No Limit", _reset_policy(self._leave_type()))
        self.assertIn(
            "Carry Forward Up To 3 Days",
            _reset_policy(self._leave_type(carryforward_max=3)),
        )

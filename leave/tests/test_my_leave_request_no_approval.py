"""Regression tests for horilla/horilla-hr#1415.

An employee submitting a leave request from My Dashboard with a leave type
whose ``require_approval`` is ``"no"`` must get an auto-approved request and
have exactly the saved ``requested_days`` deducted from their balance.

Before the fix, ``MyLeaveRequestForm.form_valid`` called
``charge_leave_request`` on the unsaved ``form.save(commit=False)`` instance,
whose ``requested_days`` is still ``None`` (it is only populated by
``LeaveRequest.save()``). ``charge_leave_request`` therefore charged
``requested_days or 0`` -- zero days -- while the saved request carried the
real number of days.
"""

from datetime import date, timedelta
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.models import AvailableLeave, Holidays, LeaveRequest, LeaveType


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class MyLeaveRequestNoApprovalTests(TestCase):
    """Runs with an in-memory cache: the default cache is django-redis and
    there is no Redis server in this environment (the accessibility
    middleware reads the cache on every request)."""

    def setUp(self):
        self.company = make_company("No Approval Co")
        self.user = make_user("noapproval", password="test-pass-123")
        self.employee = make_employee(
            company=self.company, email="noapproval@test.horilla", user=self.user
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("leave-request-create")

    def _leave_type(self, **kwargs):
        defaults = {
            "name": "Sick Leave",
            "total_days": 20,
            "require_approval": "no",
            "exclude_holiday": "no",
            "exclude_company_leave": "no",
        }
        defaults.update(kwargs)
        return LeaveType.objects.create(**defaults)

    def _balance(self, leave_type, available=10, carryforward=0):
        return AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=leave_type,
            available_days=available,
            carryforward_days=carryforward,
            total_leave_days=available + carryforward,
        )

    def _post(self, leave_type, start, end, **extra):
        data = {
            "employee_id": str(self.employee.pk),
            "leave_type_id": str(leave_type.pk),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_date_breakdown": "full_day",
            "end_date_breakdown": "full_day",
            "description": "sick leave",
        }
        data.update(extra)
        # Mail delivery is out of scope for this regression test; the view
        # starts a real mail thread on success.
        with mock.patch(
            "leave.cbv.my_leave_request.LeaveMailSendThread"
        ) as mail_thread:
            mail_thread.return_value.start.return_value = None
            # HorillaFormView requires an HTMX request (hx_request_required).
            return self.client.post(self.url, data, HTTP_HX_REQUEST="true")

    def test_no_approval_deducts_requested_days(self):
        leave_type = self._leave_type()
        avail = self._balance(leave_type)
        start = date.today() + timedelta(days=10)
        end = start + timedelta(days=2)

        response = self._post(leave_type, start, end)

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.requested_days, 3)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 7)

    def test_no_approval_deducts_effective_days_with_holiday(self):
        leave_type = self._leave_type(exclude_holiday="yes")
        avail = self._balance(leave_type)
        start = date.today() + timedelta(days=10)
        Holidays.objects.create(
            name="Mid Holiday",
            start_date=start + timedelta(days=1),
            end_date=start + timedelta(days=1),
            is_specific=False,
            company_id=self.company,
        )
        end = start + timedelta(days=2)

        response = self._post(leave_type, start, end)

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.requested_days, 2)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 8)

    def test_no_approval_half_day_on_holiday(self):
        """A half-day endpoint that falls on an excluded day still counts 0.5.

        ``LeaveRequest.save()`` adds back 0.5 for a half-day endpoint that is
        itself an off day; the balance deduction must agree with the saved
        ``requested_days`` (1.0 here), not with the plain effective-days
        helper, which would charge only 0.5.
        """
        leave_type = self._leave_type(
            exclude_holiday="yes", exclude_company_leave="yes"
        )
        avail = self._balance(leave_type)
        start = date.today() + timedelta(days=10)
        Holidays.objects.create(
            name="Start Holiday",
            start_date=start,
            end_date=start,
            is_specific=False,
            company_id=self.company,
        )
        end = start + timedelta(days=1)

        response = self._post(
            leave_type,
            start,
            end,
            start_date_breakdown="first_half",
        )

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.requested_days, 1.0)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 9)

    def test_no_approval_half_day_on_holiday_rejects_insufficient_balance(self):
        """The validation gate must agree with what save() stores.

        Same half-day-on-holiday corner as above, but with only 0.5 days of
        balance: the effective days are 1.0, so the request must be rejected
        instead of approved with the carryforward driven to -0.5. This pins
        the ``cal_effective_requested_days`` alignment with
        ``LeaveRequest.save()`` (horilla/horilla-hr#1415 debate round 1).
        """
        leave_type = self._leave_type(
            exclude_holiday="yes", exclude_company_leave="yes"
        )
        avail = self._balance(leave_type, available=0.5)
        start = date.today() + timedelta(days=10)
        Holidays.objects.create(
            name="Start Holiday",
            start_date=start,
            end_date=start,
            is_specific=False,
            company_id=self.company,
        )
        end = start + timedelta(days=1)

        response = self._post(
            leave_type,
            start,
            end,
            start_date_breakdown="first_half",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            LeaveRequest.objects.filter(
                employee_id=self.employee, leave_type_id=leave_type
            ).count(),
            0,
        )
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 0.5)

    def test_no_approval_deducts_from_carryforward(self):
        """The charge must split across available days then carryforward."""
        leave_type = self._leave_type()
        avail = self._balance(leave_type, available=1, carryforward=2)
        start = date.today() + timedelta(days=10)
        end = start + timedelta(days=2)

        response = self._post(leave_type, start, end)

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.requested_days, 3)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 0)
        self.assertEqual(avail.carryforward_days, 0)

    def test_single_form_no_approval_deducts_requested_days(self):
        """The single-leave-type form had the same charge-before-save bug."""
        leave_type = self._leave_type()
        avail = self._balance(leave_type)
        start = date.today() + timedelta(days=10)
        end = start + timedelta(days=2)
        url = reverse("user-request", kwargs={"leave": leave_type.pk})
        data = {
            "employee_id": str(self.employee.pk),
            "leave_type_id": str(leave_type.pk),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_date_breakdown": "full_day",
            "end_date_breakdown": "full_day",
            "description": "sick leave",
        }
        with mock.patch(
            "leave.cbv.my_leave_request.LeaveMailSendThread"
        ) as mail_thread:
            mail_thread.return_value.start.return_value = None
            response = self.client.post(url, data, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "approved")
        self.assertEqual(req.requested_days, 3)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 7)

    def test_approval_required_still_goes_through_approval(self):
        """Control case: the fix must not auto-charge approval-required types."""
        leave_type = self._leave_type(require_approval="yes")
        avail = self._balance(leave_type)
        start = date.today() + timedelta(days=10)
        end = start + timedelta(days=2)

        response = self._post(leave_type, start, end)

        self.assertEqual(response.status_code, 200)
        req = LeaveRequest.objects.get(
            employee_id=self.employee, leave_type_id=leave_type
        )
        self.assertEqual(req.status, "requested")
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 10)

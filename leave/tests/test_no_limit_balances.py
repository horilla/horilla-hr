"""
A leave type without a limit (limit_leave=False) stores its balance as a
large placeholder number. The balance screens show "No Limit" for it, and
the real figures for a limited leave type beside it.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

# A limited balance, and an unlimited one that has had two days taken from
# its placeholder. Neither number appears anywhere else on these screens.
LIMITED_DAYS = 12.5
UNLIMITED_DAYS = 99998.0


class NoLimitBalanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from horilla.testkit import make_company, make_employee, make_user
        from leave.forms import LEAVE_MAX_LIMIT
        from leave.models import AvailableLeave, LeaveType

        company = make_company("No Limit Co")
        admin = make_user("nolimit_admin", is_superuser=True)
        cls.admin_employee = make_employee(
            company=company, email="nolimit_admin@test.horilla", user=admin
        )
        cls.employee = make_employee(
            company=company,
            email="nolimit@test.horilla",
            first_name="Nola",
            last_name="Limit",
        )
        cls.limited_type = LeaveType.objects.create(
            name="Limited Type", total_days=20, limit_leave=True
        )
        cls.unlimited_type = LeaveType.objects.create(
            name="Unlimited Type", total_days=LEAVE_MAX_LIMIT, limit_leave=False
        )
        cls.limited = AvailableLeave.objects.create(
            employee_id=cls.employee,
            leave_type_id=cls.limited_type,
            available_days=LIMITED_DAYS,
            total_leave_days=LIMITED_DAYS,
        )
        cls.unlimited = AvailableLeave.objects.create(
            employee_id=cls.employee,
            leave_type_id=cls.unlimited_type,
            available_days=UNLIMITED_DAYS,
            total_leave_days=UNLIMITED_DAYS,
        )

    def setUp(self):
        self.client.force_login(self.admin_employee.employee_user_id)

    def get(self, url, **params):
        return self.client.get(url, params, HTTP_HX_REQUEST="true")

    def assert_limited_and_unlimited(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "12.5")
        self.assertContains(response, "No Limit")
        self.assertNotContains(response, "99998")

    def test_display_methods(self):
        self.assertEqual(self.limited.available_days_display(), LIMITED_DAYS)
        self.assertEqual(self.limited.total_leave_days_display(), LIMITED_DAYS)
        self.assertEqual(self.unlimited.available_days_display(), "No Limit")
        self.assertEqual(self.unlimited.total_leave_days_display(), "No Limit")

    def test_all_leave_balances_list(self):
        response = self.get(reverse("assign-filter"))
        self.assert_limited_and_unlimited(response)

    def test_leave_balance_detail(self):
        response = self.get(
            reverse("available-leave-single-view", args=[self.limited.pk])
        )
        self.assertContains(response, "12.5")
        self.assertNotContains(response, "No Limit")

        response = self.get(
            reverse("available-leave-single-view", args=[self.unlimited.pk])
        )
        self.assertContains(response, "No Limit")
        self.assertNotContains(response, "99998")

    def test_leave_ledger(self):
        response = self.get(reverse("leave-balance-ledger", args=[self.limited.pk]))
        self.assertContains(response, "12.5")
        self.assertNotContains(response, "No Limit")

        response = self.get(reverse("leave-balance-ledger", args=[self.unlimited.pk]))
        self.assertEqual(response.status_code, 200)
        # The current balance and the running "Bal." of each entry.
        self.assertContains(response, "No Limit", count=2)
        self.assertNotContains(response, "Bal. 99998")

    def balance_badge(self, leave_type):
        start = date.today() + timedelta(days=7)
        return self.get(
            reverse("employee-available-leave-count"),
            leave_type_id=leave_type.pk,
            employee_id=self.employee.pk,
            start_date=start.isoformat(),
            end_date=start.isoformat(),
        )

    def test_leave_request_form_balance_badge(self):
        response = self.balance_badge(self.limited_type)
        self.assertContains(response, "Available Leaves")
        self.assertContains(response, "12.5")
        self.assertNotContains(response, "No Limit")

        response = self.balance_badge(self.unlimited_type)
        self.assertContains(response, "Available Leaves")
        self.assertContains(response, "No Limit")
        self.assertNotContains(response, "99998")

    def make_leave_requests(self):
        from horilla.testkit.factories import make_leave_request

        start = date.today() + timedelta(days=14)
        return [
            make_leave_request(
                employee=self.employee,
                leave_type=leave_type,
                start_date=start,
                end_date=start,
                status="requested",
            )
            for leave_type in (self.limited_type, self.unlimited_type)
        ]

    def test_leave_requests_available_balance_column(self):
        limited_request, unlimited_request = self.make_leave_requests()
        self.assertEqual(limited_request.available_balance_col(), "12.5")
        # Leave Requests' "Available Balance" column, hidden by default.
        self.assertEqual(unlimited_request.available_balance_col(), "No Limit")

    def test_leave_request_penalty_form(self):
        leave_request = self.make_leave_requests()[0]
        response = self.get(reverse("leave-cut-penalty", args=[leave_request.pk]))
        self.assert_limited_and_unlimited(response)

    def test_penalty_records_form(self):
        response = self.get(
            reverse("penalty-records-create"), employee_id=self.employee.pk
        )
        self.assert_limited_and_unlimited(response)

    def test_late_come_early_out_penalty_form(self):
        from attendance.models import AttendanceLateComeEarlyOut
        from horilla.testkit.factories import make_attendance

        attendance = make_attendance(
            employee=self.employee, attendance_date=date.today() - timedelta(days=1)
        )
        # Its save() saves twice, so objects.create()'s forced insert fails.
        late_come = AttendanceLateComeEarlyOut(
            attendance_id=attendance, employee_id=self.employee, type="late_come"
        )
        late_come.save()
        response = self.get(reverse("cut-penalty", args=[late_come.pk]))
        self.assert_limited_and_unlimited(response)

    def test_employee_leave_allocation_cards(self):
        response = self.get(
            reverse("allocation-leave-type-list"), instance_id=self.employee.pk
        )
        self.assert_limited_and_unlimited(response)

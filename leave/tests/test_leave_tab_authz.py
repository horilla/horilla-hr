"""An employee's leave tab is limited to the employee, their manager and permission holders.

Both the standalone `leave-tab` view and the profile tab (`individual-leave-tab-list`)
apply the same rule.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.models import LeaveRequest, LeaveType


class LeaveTabAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Leave Tab Co")
        cls.owner_user = make_user("tab_owner", password="secret123")
        cls.owner = make_employee(
            company=company, email="tab_owner@test.horilla", user=cls.owner_user
        )
        cls.other_user = make_user("tab_other", password="secret123")
        cls.other = make_employee(
            company=company, email="tab_other@test.horilla", user=cls.other_user
        )
        cls.manager_user = make_user("tab_manager", password="secret123")
        cls.manager = make_employee(
            company=company, email="tab_manager@test.horilla", user=cls.manager_user
        )
        work_info = cls.owner.employee_work_info
        work_info.reporting_manager_id = cls.manager
        work_info.save()
        leave_type = LeaveType.objects.create(name="Maternity Leave")
        LeaveRequest.objects.create(
            employee_id=cls.owner,
            leave_type_id=leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            description="Pregnancy-related appointment",
        )

    def _get(self, user, route):
        client = Client()
        client.force_login(type(user).objects.get(pk=user.pk))
        url = reverse(route, kwargs={"pk": self.owner.pk})
        return client.get(url, HTTP_HX_REQUEST="true")

    @staticmethod
    def _denied(response):
        return b"Have Permission" in response.content

    # What only the real tab carries: the function view's leave table shell, the profile tab's rows.
    MARKER = {
        "leave-tab": b"oh-sticky-table-request",
        "individual-leave-tab-list": b"Maternity",
    }

    def _allowed(self, response, route):
        """The real tab came back: not the permission page, and it carries its own content."""
        return (
            response.status_code == 200
            and not self._denied(response)
            and self.MARKER[route] in response.content
        )

    def test_unrelated_employee_cannot_open_the_function_view(self):
        response = self._get(self.other_user, "leave-tab")
        self.assertTrue(
            self._denied(response),
            "the leave tab was served to an unrelated employee",
        )
        self.assertNotIn(b"Maternity", response.content)

    def test_unrelated_employee_cannot_open_the_profile_tab(self):
        response = self._get(self.other_user, "individual-leave-tab-list")
        self.assertTrue(
            self._denied(response),
            "the profile leave tab was served to an unrelated employee",
        )
        self.assertNotIn(b"Maternity", response.content)

    def test_owner_still_sees_their_own_leave(self):
        """A fix that denies everyone would pass the tests above."""
        for route in ("leave-tab", "individual-leave-tab-list"):
            with self.subTest(route=route):
                self.assertTrue(self._allowed(self._get(self.owner_user, route), route))

    def test_reporting_manager_still_sees_the_leave(self):
        for route in ("leave-tab", "individual-leave-tab-list"):
            with self.subTest(route=route):
                self.assertTrue(
                    self._allowed(self._get(self.manager_user, route), route)
                )

    def test_permission_holder_still_sees_the_leave(self):
        """HR must keep working."""
        self.other_user.user_permissions.add(
            Permission.objects.get(codename="view_leaverequest")
        )
        for route in ("leave-tab", "individual-leave-tab-list"):
            with self.subTest(route=route):
                self.assertTrue(self._allowed(self._get(self.other_user, route), route))

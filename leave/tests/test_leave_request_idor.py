"""Leave requests must be scoped to their owner, not resolved by id alone.

GHSA-mpw3-7c6v-vfjp: `user_request_one` fetched
`LeaveRequest.objects.filter(id=id)` under only `@login_required`, so any
employee could read any other employee's leave request by incrementing the id.

Leave records carry the reason for absence, so this is not merely "who is off
next week" -- it exposes medical information, which is special-category data
under GDPR Art. 9.

The advisory records the affected range as `<= 1.3`. It reproduced on 2.0.

A second site the report does not mention had the same gap in the other
direction: `create_leaverequest_comment` called `form.save()` with no owner
check, so a comment could be written onto anyone's request. (The
`employee_get.id == leave.employee_id.id` line further down that view only
decides who gets notified; it is not authorization.)
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase

from horilla.testkit import make_company, make_employee, make_user
from leave.models import LeaveRequest, LeaveType
from leave.views import can_view_leave_request


class _Request:
    """The helper reads only .user; employee_get comes off the user."""

    def __init__(self, user):
        self.user = user


class LeaveRequestVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Leave Co")
        cls.owner_user = make_user("leave_owner", password="secret123")
        cls.owner = make_employee(
            company=company, email="leave_owner@test.horilla", user=cls.owner_user
        )
        cls.snooper_user = make_user("leave_snooper", password="secret123")
        cls.snooper = make_employee(
            company=company,
            email="leave_snooper@test.horilla",
            user=cls.snooper_user,
        )
        leave_type = LeaveType.objects.create(name="Sick Leave")
        cls.request_obj = LeaveRequest.objects.create(
            employee_id=cls.owner,
            leave_type_id=leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            description="Oncology follow-up appointment",
        )

    @staticmethod
    def _reload(user):
        """Permission caching is per-instance, so refetch after granting."""
        return type(user).objects.get(pk=user.pk)

    def test_unrelated_employee_cannot_view_the_request(self):
        """The reported attack: any employee, any id."""
        self.assertFalse(
            can_view_leave_request(_Request(self.snooper_user), self.request_obj)
        )

    def test_owner_can_view_their_own_request(self):
        """A fix that denies everyone would also pass the test above."""
        self.assertTrue(
            can_view_leave_request(_Request(self.owner_user), self.request_obj)
        )

    def test_permission_holder_can_view(self):
        """HR must keep working."""
        self.snooper_user.user_permissions.add(
            Permission.objects.get(codename="view_leaverequest")
        )
        self.assertTrue(
            can_view_leave_request(
                _Request(self._reload(self.snooper_user)), self.request_obj
            )
        )

    def test_reporting_manager_can_view(self):
        """The third arm of the rule the codebase already used."""
        work_info = self.owner.employee_work_info
        work_info.reporting_manager_id = self.snooper
        work_info.save()
        self.assertTrue(
            can_view_leave_request(
                _Request(self._reload(self.snooper_user)), self.request_obj
            )
        )

    def test_the_description_is_what_this_protects(self):
        """Stated explicitly: the field carries the reason for absence, which
        is why a cross-employee read is a GDPR Art. 9 exposure rather than a
        scheduling inconvenience."""
        self.assertIn("Oncology", self.request_obj.description)
        self.assertFalse(
            can_view_leave_request(_Request(self.snooper_user), self.request_obj)
        )

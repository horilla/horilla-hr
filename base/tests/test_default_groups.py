"""
Default HRMS groups: the Attendance Manager can plan the roster.

The Roster Planner is limited to holders of ``base.change_roster`` (everyone
else sees only their own reports). Shift planning is attendance work, so the
Attendance Manager group carries the roster permissions, and only those: its
access to the rest of ``base`` stays view-only.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from base.models import CompanyGroupAssignment, Department, EmployeeShift, Roster
from base.signals import _sync_default_hrms_groups
from horilla.testkit import make_company, make_employee, make_user

ROSTER = {
    ("base", "add_roster"),
    ("base", "change_roster"),
    ("base", "delete_roster"),
    ("base", "add_rosterpublishlog"),
    ("base", "change_rosterpublishlog"),
}


def _perms(group):
    return set(group.permissions.values_list("content_type__app_label", "codename"))


class AttendanceManagerGroupTests(TestCase):
    def setUp(self):
        _sync_default_hrms_groups()
        self.group = Group.objects.get(name="Attendance Manager")

    def test_it_can_plan_and_publish_the_roster(self):
        self.assertTrue(ROSTER <= _perms(self.group))

    def test_the_rest_of_base_stays_view_only(self):
        perms = _perms(self.group)
        for codename in ("change_department", "delete_department", "add_holidays"):
            self.assertNotIn(("base", codename), perms)
        self.assertIn(("base", "view_department"), perms)

    def test_other_default_groups_are_unchanged(self):
        self.assertNotIn(
            ("base", "change_roster"), _perms(Group.objects.get(name="Leave Manager"))
        )
        self.assertIn(
            ("base", "change_roster"), _perms(Group.objects.get(name="HR Manager"))
        )

    def test_an_upgrade_restores_the_permission_and_keeps_custom_ones(self):
        """The sync only ever adds, so an existing install gets it on migrate."""
        change_roster = Permission.objects.get(
            content_type__app_label="base", codename="change_roster"
        )
        custom = Permission.objects.get(
            content_type__app_label="base", codename="change_department"
        )
        self.group.permissions.remove(change_roster)
        self.group.permissions.add(custom)
        _sync_default_hrms_groups()
        perms = _perms(self.group)
        self.assertIn(("base", "change_roster"), perms)
        self.assertIn(("base", "change_department"), perms)


class AttendanceManagerPlannerTests(TestCase):
    def test_a_member_sees_the_whole_planner(self):
        _sync_default_hrms_groups()
        company = make_company("Planner Co")
        user = make_user("attmanager")
        make_employee(company=company, email="attmanager@test.horilla", user=user)
        # Group permissions are resolved per company, so the role is granted
        # through a company assignment, not plain group membership.
        CompanyGroupAssignment.objects.create(
            user=user,
            company=company,
            group=Group.objects.get(name="Attendance Manager"),
        )
        first = make_employee(company=company, email="first@test.horilla")
        second = make_employee(company=company, email="second@test.horilla")
        department = Department.objects.create(department="Planning")
        shift = EmployeeShift.objects.create(employee_shift="Day")
        day = date.today() + timedelta(days=2)
        for employee in (first, second):
            Roster.objects.create(
                employee=employee, date=day, shift=shift, department=department
            )
        self.client.force_login(user)
        response = self.client.get(reverse("roster-grid"), HTTP_HX_REQUEST="true")
        shown = {row["employee"].pk for row in response.context["rows"]}
        self.assertEqual(shown, {first.pk, second.pk})

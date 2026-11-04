"""
Permission checks on the archive route and the allocation allowance list.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
DENIED_TEMPLATE = "decorator_404.html"


def _actor(codenames, username="actor"):
    company = make_company(f"{username} Co")
    user = make_user(username)
    employee = make_employee(
        company=company, email=f"{username}@test.horilla", user=user
    )
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user, employee, company


class ArchiveRoutePermissionTests(TestCase):
    """
    get-manager-in archives or un-archives an employee, and also shows the
    records that block an archive (the offboarding screens use that). Showing
    needs view access; the write needs the same permission as employee_archive.
    """

    def setUp(self):
        self.user, _employee, self.company = _actor(["view_employee"])
        self.target = make_employee(company=self.company, email="target@test.horilla")
        self.client.force_login(self.user)
        self.url = reverse("get-manager-in")

    def _active(self):
        return Employee.objects.get(pk=self.target.pk).is_active

    def test_view_only_access_cannot_archive(self):
        response = self.client.get(self.url, {"employee_id": self.target.pk}, **HX)
        self.assertTrue(self._active())
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_view_only_access_cannot_unarchive(self):
        Employee.objects.filter(pk=self.target.pk).update(is_active=False)
        self.client.get(self.url, {"employee_id": self.target.pk}, **HX)
        self.assertFalse(self._active())

    def test_delete_permission_archives(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename="delete_employee")
        )
        self.client.get(self.url, {"employee_id": self.target.pk}, **HX)
        self.assertFalse(self._active())

    def test_view_only_access_still_shows_the_blocking_records(self):
        """The offboarding 'Show managing records' button keeps working."""
        report = make_employee(company=self.company, email="report@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=report).update(
            reporting_manager_id=self.target
        )
        self.assertTrue(self.target.get_archive_condition())
        response = self.client.get(
            self.url, {"employee_id": self.target.pk, "offboarding": "True"}, **HX
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateNotUsed(response, DENIED_TEMPLATE)
        self.assertTrue(self._active())


class AllocationAllowanceListGateTests(TestCase):
    """Same gate as the deduction list next to it."""

    def setUp(self):
        self.target = None

    def _url(self, target):
        return reverse("allocation-allowance-list") + f"?instance_id={target.pk}"

    def test_a_signed_in_user_with_no_relationship_is_refused(self):
        user, _employee, company = _actor([])
        target = make_employee(company=company, email="target@test.horilla")
        self.client.force_login(user)
        response = self.client.get(self._url(target), **HX)
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_a_recruitment_manager_is_still_admitted(self):
        """Recruitment and onboarding managers keep using this screen."""
        user, _employee, company = _actor(["view_recruitment"])
        target = make_employee(company=company, email="target@test.horilla")
        self.client.force_login(user)
        response = self.client.get(self._url(target), **HX)
        self.assertTemplateNotUsed(response, DENIED_TEMPLATE)

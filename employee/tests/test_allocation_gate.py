"""
The allocation screen's gate and its login-access toggle.

Recruitment and onboarding managers, and an employee's reporting manager, use
this screen. The gate used to check only the first ``instance_id`` it found
(the query string wins over the form body) while most writes read the body, so
someone with access to one employee could write to another. Every value
supplied, in either place, now has to pass.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
DENIED = "decorator_404.html"
LISTS = [
    "allocation-leave-type-list",
    "allocation-asset-list",
    "allocation-allowance-list",
]


def _grant(user, dotted):
    app_label, codename = dotted.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )


class AllocationBase(TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Allocation Co")
        self.manager_user = make_user("almanager")
        self.manager = make_employee(
            company=company, email="almanager@test.horilla", user=self.manager_user
        )
        self.report_user = make_user("alreport")
        self.report = make_employee(
            company=company, email="alreport@test.horilla", user=self.report_user
        )
        self.stranger_user = make_user("alstranger")
        self.stranger = make_employee(
            company=company, email="alstranger@test.horilla", user=self.stranger_user
        )
        self.boss_user = make_user("alboss", is_superuser=True)
        self.boss = make_employee(
            company=company, email="alboss@test.horilla", user=self.boss_user
        )
        for employee in (self.report, self.boss):
            EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                reporting_manager_id=self.manager
            )
        self.client.force_login(self.manager_user)

    def assertDenied(self, response):
        names = [t.name for t in response.templates]
        self.assertTrue(
            response.status_code == 403 or DENIED in names,
            f"expected a refusal, got {response.status_code} {names}",
        )

    def assertAllowed(self, response):
        names = [t.name for t in response.templates]
        self.assertNotEqual(response.status_code, 403)
        self.assertNotIn(DENIED, names)

    def _post(self, name, query_id, body_id):
        url = reverse(name)
        if query_id is not None:
            url += f"?instance_id={query_id}"
        data = {} if body_id is None else {"instance_id": body_id}
        return self.client.post(url, data, **HX)


class AllocationGateTests(AllocationBase):
    def test_the_query_string_and_the_body_must_both_name_a_reachable_employee(self):
        for name in LISTS:
            with self.subTest(view=name):
                response = self._post(name, self.report.pk, self.stranger.pk)
                self.assertDenied(response)

    def test_the_other_way_round_is_refused_too(self):
        for name in LISTS:
            with self.subTest(view=name):
                response = self._post(name, self.stranger.pk, self.report.pk)
                self.assertDenied(response)

    def test_a_manager_gets_through_for_their_own_report_in_both_places(self):
        for name in LISTS:
            with self.subTest(view=name):
                self.assertAllowed(self._post(name, self.report.pk, self.report.pk))

    def test_a_recruitment_manager_keeps_access_to_any_employee(self):
        _grant(self.manager_user, "recruitment.view_recruitment")
        for name in LISTS:
            with self.subTest(view=name):
                self.assertAllowed(self._post(name, self.report.pk, self.stranger.pk))

    def test_a_malformed_instance_id_is_refused_not_a_server_error(self):
        for name in LISTS:
            with self.subTest(view=name):
                self.assertDenied(self._post(name, "abc", None))

    def test_no_instance_id_at_all_is_refused(self):
        for name in LISTS:
            with self.subTest(view=name):
                self.assertDenied(self._post(name, None, None))


class ToggleLoginAccessTests(AllocationBase):
    def _toggle(self, employee):
        url = reverse("toggle-user-dashboard-access") + f"?instance_id={employee.pk}"
        return self.client.post(url, **HX)

    def _active(self, user):
        user.refresh_from_db()
        return user.is_active

    def test_a_reporting_manager_can_switch_a_reports_login_off_and_on(self):
        self._toggle(self.report)
        self.assertFalse(self._active(self.report_user))
        self._toggle(self.report)
        self.assertTrue(self._active(self.report_user))

    def test_a_stranger_cannot_be_switched_by_a_plain_manager(self):
        self.assertDenied(self._toggle(self.stranger))
        self.assertTrue(self._active(self.stranger_user))

    def test_a_recruitment_manager_can_still_switch_an_ordinary_account(self):
        _grant(self.manager_user, "recruitment.view_recruitment")
        self._toggle(self.stranger)
        self.assertFalse(self._active(self.stranger_user))

    def test_a_superusers_account_cannot_be_switched_off_by_a_manager(self):
        self.assertDenied(self._toggle(self.boss))
        self.assertTrue(self._active(self.boss_user))

    def test_a_recruitment_manager_cannot_switch_off_a_superuser_either(self):
        _grant(self.manager_user, "recruitment.view_recruitment")
        self.assertDenied(self._toggle(self.boss))
        self.assertTrue(self._active(self.boss_user))

    def test_nobody_switches_off_their_own_login(self):
        _grant(self.manager_user, "recruitment.view_recruitment")
        self.assertDenied(self._toggle(self.manager))
        self.assertTrue(self._active(self.manager_user))

    def test_a_superuser_may_switch_another_account(self):
        self.manager_user.is_superuser = True
        self.manager_user.save()
        self._toggle(self.boss)
        self.assertFalse(self._active(self.boss_user))

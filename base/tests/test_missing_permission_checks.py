"""
Permission checks on form views that carried ``login_required`` alone.

Each of these class-based views serves a create route and an update route, and
used to let any signed-in user write. A denial is asserted two ways: nothing was
saved, and the response is the permission-denied page. Each has a control that
holds the right permission and does write, so the guard is shown to cut in
exactly where it should.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from base.models import CompanyLeaves, Holidays
from horilla.testkit import make_company, make_employee, make_user
from horilla_ldap.models import LDAPSettings

HX = {"HTTP_HX_REQUEST": "true"}
DENIED_TEMPLATE = "decorator_404.html"


def _user_with(codenames=(), username="actor", superuser=False):
    company = make_company(f"{username} Co")
    user = make_user(username, is_superuser=superuser)
    make_employee(company=company, email=f"{username}@test.horilla", user=user)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


class HolidayPermissionTests(TestCase):
    PAYLOAD = {
        "name": "Probe Day",
        "start_date": "2027-01-01",
        "end_date": "2027-01-01",
        "available_for_all": "on",
    }

    def _holiday(self):
        return Holidays.objects.create(
            name="Original", start_date=date(2027, 2, 1), end_date=date(2027, 2, 1)
        )

    def test_create_is_refused_without_the_add_permission(self):
        self.client.force_login(_user_with())
        response = self.client.post(reverse("holiday-creation"), self.PAYLOAD, **HX)
        self.assertEqual(Holidays.objects.count(), 0)
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_create_works_with_the_add_permission(self):
        self.client.force_login(_user_with(["add_holidays"]))
        self.client.post(reverse("holiday-creation"), self.PAYLOAD, **HX)
        self.assertEqual(Holidays.objects.count(), 1)

    def test_add_permission_alone_cannot_edit(self):
        holiday = self._holiday()
        self.client.force_login(_user_with(["add_holidays"]))
        self.client.post(
            reverse("holiday-update", args=[holiday.pk]),
            dict(self.PAYLOAD, name="Changed"),
            **HX,
        )
        holiday.refresh_from_db()
        self.assertEqual(holiday.name, "Original")

    def test_update_is_refused_without_the_change_permission(self):
        holiday = self._holiday()
        self.client.force_login(_user_with())
        response = self.client.post(
            reverse("holiday-update", args=[holiday.pk]),
            dict(self.PAYLOAD, name="Changed"),
            **HX,
        )
        holiday.refresh_from_db()
        self.assertEqual(holiday.name, "Original")
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_update_works_with_the_change_permission(self):
        holiday = self._holiday()
        self.client.force_login(_user_with(["change_holidays"]))
        self.client.post(
            reverse("holiday-update", args=[holiday.pk]),
            dict(self.PAYLOAD, name="Changed"),
            **HX,
        )
        holiday.refresh_from_db()
        self.assertEqual(holiday.name, "Changed")

    def test_duplicate_is_refused_without_the_add_permission(self):
        holiday = self._holiday()
        self.client.force_login(_user_with())
        response = self.client.post(
            reverse("duplicate-holiday", args=[holiday.pk]), self.PAYLOAD, **HX
        )
        self.assertEqual(Holidays.objects.count(), 1)
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_duplicate_needs_add_not_change(self):
        """It carries a pk but always creates a record."""
        holiday = self._holiday()
        self.client.force_login(_user_with(["change_holidays"]))
        self.client.post(
            reverse("duplicate-holiday", args=[holiday.pk]), self.PAYLOAD, **HX
        )
        self.assertEqual(Holidays.objects.count(), 1)

        self.client.force_login(_user_with(["add_holidays"], username="adder"))
        self.client.post(
            reverse("duplicate-holiday", args=[holiday.pk]), self.PAYLOAD, **HX
        )
        self.assertEqual(Holidays.objects.count(), 2)


class CompanyLeavePermissionTests(TestCase):
    PAYLOAD = {"based_on_week": "0", "based_on_week_day": "0"}

    def test_create_is_refused_without_the_add_permission(self):
        self.client.force_login(_user_with())
        response = self.client.post(
            reverse("company-leave-creation"), self.PAYLOAD, **HX
        )
        self.assertEqual(CompanyLeaves.objects.count(), 0)
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_create_works_with_the_add_permission(self):
        self.client.force_login(_user_with(["add_companyleaves"]))
        self.client.post(reverse("company-leave-creation"), self.PAYLOAD, **HX)
        self.assertEqual(CompanyLeaves.objects.count(), 1)

    def test_update_is_refused_without_the_change_permission(self):
        leave = CompanyLeaves.objects.create(based_on_week="0", based_on_week_day="0")
        self.client.force_login(_user_with(["add_companyleaves"]))
        response = self.client.post(
            reverse("company-leave-update", args=[leave.pk]),
            {"based_on_week": "1", "based_on_week_day": "1"},
            **HX,
        )
        leave.refresh_from_db()
        self.assertEqual((leave.based_on_week, leave.based_on_week_day), ("0", "0"))
        self.assertTemplateUsed(response, DENIED_TEMPLATE)


class ApprovalConditionPermissionTests(TestCase):
    """
    The create and edit forms. Both methods share one dispatch check, so the
    GET is enough to show the gate; the form is not rendered for a refusal.
    """

    def test_create_form_is_refused_without_the_add_permission(self):
        self.client.force_login(_user_with())
        response = self.client.get(reverse("multiple-level-approval-create"), **HX)
        self.assertTemplateUsed(response, DENIED_TEMPLATE)

    def test_create_form_opens_with_the_add_permission(self):
        self.client.force_login(_user_with(["add_multipleapprovalcondition"]))
        response = self.client.get(reverse("multiple-level-approval-create"), **HX)
        self.assertTemplateNotUsed(response, DENIED_TEMPLATE)
        self.assertEqual(response.status_code, 200)

    def test_edit_form_needs_the_change_permission_not_the_add_one(self):
        url = reverse("multiple-level-approval-edit", args=[1])
        self.client.force_login(_user_with(["add_multipleapprovalcondition"]))
        self.assertTemplateUsed(self.client.get(url, **HX), DENIED_TEMPLATE)


class LdapSettingsPermissionTests(TestCase):
    DATA = {}

    def _post(self):
        from horilla_ldap.forms import LDAPSettingsForm

        data = {
            name: "on" if f.__class__.__name__ == "BooleanField" else "ldap.example.com"
            for name, f in LDAPSettingsForm().fields.items()
        }
        return self.client.post(reverse("ldap-settings"), data)

    def test_a_signed_in_user_cannot_write_the_settings(self):
        self.client.force_login(_user_with())
        self._post()
        self.assertEqual(LDAPSettings.objects.count(), 0)

    def test_a_user_with_the_model_permission_but_not_superuser_is_refused(self):
        self.client.force_login(_user_with(["change_ldapsettings"]))
        self._post()
        self.assertEqual(LDAPSettings.objects.count(), 0)

    def test_a_superuser_can_write_the_settings(self):
        self.client.force_login(_user_with(superuser=True))
        self._post()
        self.assertEqual(LDAPSettings.objects.count(), 1)

    def test_the_stored_bind_password_is_not_shown_to_other_users(self):
        LDAPSettings.objects.create(bind_password="stored-secret-value")
        self.client.force_login(_user_with())
        response = self.client.get(reverse("ldap-settings"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"stored-secret-value", response.content)

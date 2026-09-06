"""Unit tests for base.methods.has_export_access."""

from datetime import date, timedelta
from types import SimpleNamespace

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from base.methods import has_export_access
from base.models import DefaultExportPermission, Holidays
from horilla.testkit import make_company, make_user


class HasExportAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Export Corp")
        cls.superuser = make_user("export_admin", is_superuser=True)
        cls.user = make_user("export_user")
        cls.holiday = Holidays.objects.create(
            name="Export Day",
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=10),
            company_id=cls.company,
        )

    def _request(self, user, selected_company=None):
        session = {}
        if selected_company is not None:
            session["selected_company"] = selected_company
        return SimpleNamespace(user=user, session=session)

    def test_superuser_always_allowed(self):
        DefaultExportPermission.objects.update_or_create(
            company_id=self.company, defaults={"is_enabled": False}
        )
        request = self._request(self.superuser, selected_company=str(self.company.pk))
        self.assertTrue(has_export_access(request, Holidays))

    def test_default_enabled_allows_everyone(self):
        DefaultExportPermission.objects.update_or_create(
            company_id=self.company, defaults={"is_enabled": True}
        )
        request = self._request(self.user, selected_company=str(self.company.pk))
        self.assertTrue(has_export_access(request, Holidays))

    def test_no_setting_allows_everyone(self):
        """
        Backwards-compatible fallback. Rows are now seeded per company
        (migration base.0003 + the Company post_save receiver), so this
        deletes the seeded row to exercise the path an old install hits
        before migrating.
        """
        DefaultExportPermission.objects.filter(company_id=self.company).delete()
        request = self._request(self.user, selected_company=str(self.company.pk))
        self.assertTrue(has_export_access(request, Holidays))

    def test_disabled_without_perm_denies(self):
        DefaultExportPermission.objects.update_or_create(
            company_id=self.company, defaults={"is_enabled": False}
        )
        request = self._request(self.user, selected_company=str(self.company.pk))
        self.assertFalse(has_export_access(request, Holidays))

    def test_disabled_with_export_perm_allows(self):
        DefaultExportPermission.objects.update_or_create(
            company_id=self.company, defaults={"is_enabled": False}
        )
        ct = ContentType.objects.get_for_model(Holidays)
        perm, _ = Permission.objects.get_or_create(
            codename="export_holidays",
            content_type=ct,
            defaults={"name": "Can export holidays"},
        )
        self.user.user_permissions.add(perm)
        # Refresh permission cache
        self.user = type(self.user).objects.get(pk=self.user.pk)
        request = self._request(self.user, selected_company=str(self.company.pk))
        self.assertTrue(has_export_access(request, Holidays))

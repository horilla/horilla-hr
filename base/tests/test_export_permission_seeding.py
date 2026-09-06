"""
"Default Export Access" must be an explicit stored value, not a permissive
default inferred from a missing row.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from base.models import Company, DefaultExportPermission


class ExportPermissionSeedingTests(TestCase):
    def test_migration_seeded_the_null_company_row(self):
        """The 'All companies' session scope reads company_id=None."""
        self.assertTrue(
            DefaultExportPermission.objects.filter(company_id=None).exists()
        )

    def test_new_company_gets_an_explicit_row(self):
        company = Company.objects.create(company="Seeded Co", hq=False)
        setting = DefaultExportPermission.objects.filter(company_id=company).first()
        self.assertIsNotNone(setting, "new company has no export-access row")
        self.assertTrue(
            setting.is_enabled, "seeded row must preserve current behaviour"
        )

    def test_seeding_does_not_overwrite_an_admin_choice(self):
        company = Company.objects.create(company="Opinionated Co", hq=False)
        setting = DefaultExportPermission.objects.get(company_id=company)
        setting.is_enabled = False
        setting.save()
        # Re-saving the company must not reset the admin's decision.
        company.company = "Opinionated Co Renamed"
        company.save()
        setting.refresh_from_db()
        self.assertFalse(setting.is_enabled)

    def test_no_duplicate_rows_per_company(self):
        company = Company.objects.create(company="Once Only", hq=False)
        company.save()
        company.save()
        self.assertEqual(
            DefaultExportPermission.objects.filter(company_id=company).count(), 1
        )

    def test_duplicate_row_per_company_is_rejected(self):
        """
        Readers use .filter(company_id=...).first(), so a second row would
        decide the setting by insertion order.
        """
        company = Company.objects.create(company="No Dupes", hq=False)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DefaultExportPermission.objects.create(
                    company_id=company, is_enabled=False
                )

    def test_duplicate_null_company_row_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DefaultExportPermission.objects.create(
                    company_id=None, is_enabled=False
                )

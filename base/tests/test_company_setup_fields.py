"""Company Setup's new compliance fields directly on base.Company."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from horilla.testkit import make_company


class CompanyComplianceFieldsTests(TestCase):
    def test_defaults(self):
        company = make_company()
        self.assertEqual(company.status, "ONBOARDING")
        self.assertEqual(company.invoice_cycle, "MONTHLY")
        self.assertFalse(company.ldc_applied)
        self.assertFalse(company.require_payroll_signoff)
        self.assertFalse(company.overdue)

    def test_blocks_operations(self):
        company = make_company()
        self.assertFalse(company.blocks_operations())
        company.status = "ON_HOLD"
        self.assertTrue(company.blocks_operations())
        company.status = "DEACTIVATED"
        self.assertTrue(company.blocks_operations())
        company.status = "ACTIVE"
        self.assertFalse(company.blocks_operations())

    def test_clean_rejects_pan_and_foreign_tax_id_together(self):
        company = make_company(pan="ABCDE1234F", foreign_tax_id="FTI-123")
        with self.assertRaises(Exception):
            company.full_clean()

    def test_duplicate_pan_blocked_at_db_level(self):
        make_company("Company A", pan="ABCDE1234F")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_company("Company B", address="2 Other St", pan="ABCDE1234F")

    def test_duplicate_legal_name_is_allowed(self):
        # Legal Name isn't checked for duplicates — only PAN/Foreign Tax ID
        # — since formatting can legitimately vary (per the PRD).
        make_company("Company A", legal_name="Acme Pvt Ltd", pan="ABCDE1234F")
        make_company(
            "Company B", address="2 Other St", legal_name="Acme Pvt Ltd", pan="FGHIJ5678K"
        )  # should not raise

    def test_null_pan_does_not_collide(self):
        make_company("Company A")
        make_company("Company B", address="2 Other St")  # both pan=None, should not raise

    def test_blank_string_pan_normalizes_to_none_and_does_not_collide(self):
        # A ModelForm submission for a left-blank CharField saves "" (the
        # default empty_value), not None — Company.clean() normalizes this
        # to None before validate_unique() runs, so two companies both
        # left blank must not collide with each other on "".
        company_a = make_company("Company A", pan="")
        company_a.full_clean()
        company_a.save()

        company_b = make_company("Company B", address="2 Other St", pan="")
        company_b.full_clean()  # should not raise
        company_b.save()

        company_a.refresh_from_db()
        company_b.refresh_from_db()
        self.assertIsNone(company_a.pan)
        self.assertIsNone(company_b.pan)

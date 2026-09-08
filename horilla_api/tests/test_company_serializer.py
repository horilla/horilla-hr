"""
Regression test proving Company Setup's new compliance fields on
base.Company are NOT exposed through the existing generic Company API —
CompanySerializer was deliberately frozen to an explicit field list
instead of "__all__" for exactly this reason.
"""

from django.test import TestCase

from horilla.testkit import make_company

from horilla_api.api_serializers.base.serializers import CompanySerializer


class CompanySerializerFieldFreezeTests(TestCase):
    def test_new_compliance_fields_are_not_exposed(self):
        company = make_company(
            pan="ABCDE1234F",
            legal_name="Acme Pvt Ltd",
            status="ACTIVE",
        )
        data = CompanySerializer(company).data
        for field in [
            "pan",
            "foreign_tax_id",
            "legal_name",
            "tax_country",
            "status",
            "invoice_cycle",
            "payment_terms",
            "overdue",
            "ldc_applied",
            "require_payroll_signoff",
        ]:
            self.assertNotIn(field, data)

    def test_original_fields_still_exposed(self):
        company = make_company()
        data = CompanySerializer(company).data
        for field in ["id", "company", "address", "country", "state", "city", "zip"]:
            self.assertIn(field, data)

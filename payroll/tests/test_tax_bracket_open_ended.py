"""
A tax bracket saved without a maximum income.

The single bracket form stored math.inf for "no maximum". Infinity is not
valid JSON, so the API's tax bracket list failed to render, and so did the
audit log entry for the save once an administrator turned on auditing for tax
brackets. The slab table already stores NULL for an open-ended slab.
"""

import math

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import FilingStatus
from payroll.models.tax_models import TaxBracket


class OpenEndedTaxBracketTests(TestCase):
    def setUp(self):
        self.user = make_user("taxbracketadmin", is_superuser=True)
        make_employee(
            company=make_company("Open Bracket Co"),
            email="taxbracketadmin@test.horilla",
            user=self.user,
        )
        self.client.force_login(self.user)
        self.status = FilingStatus.objects.create(filing_status="Single")

    def create_through_form(self, max_income=""):
        response = self.client.post(
            reverse("tax-bracket-create", args=[self.status.pk]),
            {
                "filing_status_id": self.status.pk,
                "min_income": "50000",
                "max_income": max_income,
                "tax_rate": "40",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        return TaxBracket.objects.get(filing_status_id=self.status)

    def test_a_blank_maximum_is_stored_as_null(self):
        bracket = self.create_through_form()
        self.assertIsNone(bracket.max_income)

    def test_the_api_lists_an_open_ended_bracket(self):
        self.create_through_form()
        api = APIClient()
        api.force_authenticate(user=self.user)

        response = api.get("/api/payroll/tax-bracket/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[0]["max_income"])

    def test_an_audited_bracket_saves_without_a_maximum(self):
        from auditlog.models import LogEntry

        from horilla_audit.models import AuditModelConfig

        # What turning on auditing for tax brackets in the settings does.
        config = AuditModelConfig.objects.create(
            app_label="payroll", model_name="TaxBracket"
        )
        self.addCleanup(config.delete)

        bracket = self.create_through_form()

        entry = LogEntry.objects.get_for_object(bracket).latest("timestamp")
        self.assertIsNone(entry.serialized_data["fields"]["max_income"])

    def test_a_stored_infinity_becomes_null_on_the_next_save(self):
        bracket = TaxBracket.objects.create(
            filing_status_id=self.status, min_income=0, max_income=10000, tax_rate=10
        )
        # Brackets saved before this fix hold infinity.
        TaxBracket.objects.filter(pk=bracket.pk).update(max_income=math.inf)
        bracket.refresh_from_db()

        bracket.tax_rate = 12
        bracket.save()
        bracket.refresh_from_db()

        self.assertIsNone(bracket.max_income)

    def test_null_and_infinity_both_read_as_open_ended(self):
        for top in (None, math.inf):
            bracket = TaxBracket(
                filing_status_id=self.status, min_income=50000, max_income=top
            )
            self.assertIsNone(bracket.get_display_max_income())
            self.assertIn("equal or above", str(bracket))

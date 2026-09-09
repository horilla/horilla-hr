from django.test import TestCase

from horilla.horilla_middlewares import _thread_locals
from horilla.testkit import CompanyFilterTestMixin, make_company, make_employee, make_user

from company_onboarding.models import GSTStateConfig


class WizardFlowTests(CompanyFilterTestMixin, TestCase):
    def setUp(self):
        # horilla.decorators.login_required requires the logged-in user to
        # have a linked Employee (request.user.employee_get) — a bare
        # make_user() alone gets silently redirected to /login/. See
        # base.management.commands.createhorillauser for the same
        # user+Employee pairing this mirrors.
        self.user = make_user("ventura_admin", is_superuser=True)
        make_employee(
            company=make_company("Ventura HQ"),
            email="ventura_admin@test.horilla",
            user=self.user,
        )
        self.client.force_login(self.user)
        # state is a ModelChoiceField now (FK to GSTStateConfig) -- the
        # form posts its pk, not the GST code string.
        self.maharashtra_state, _ = GSTStateConfig.objects.get_or_create(
            code="27", defaults={"name": "Maharashtra"}
        )
        # A logged-in user whose own Employee has a company link otherwise
        # gets CompanyMiddleware's own-company-resolution fallback applied
        # to their session — fine for company-scoped screens, wrong here,
        # since Company Setup wizards work ACROSS company boundaries by
        # design. Forcing "all" here is what a real user would do via the
        # company switcher before this kind of cross-company admin work.
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def tearDown(self):
        # HorillaModel.save() reads _thread_locals.request.user to
        # auto-populate created_by. That's a plain threading.local, not
        # reset by TestCase's per-test transaction rollback, so a request
        # made via self.client here would otherwise leak a (soon
        # rolled-back) user reference into the next test's factory calls,
        # causing a created_by FK violation there instead of here.
        # CompanyFilterTestMixin.tearDown() (via super()) resets the
        # separate selected-company contextvar for the same class of
        # reason — company_onboarding's own models don't use
        # HorillaCompanyManager (see models.py's Architecture note), but
        # other company-scoped models elsewhere in the app still do, and
        # this keeps that contextvar from leaking across test methods too.
        _thread_locals.request = None
        super().tearDown()

    def _identity_payload(self, **overrides):
        payload = {
            "company": "Acme Client",
            "address": "1 Test St",
            "country": "India",
            "state": "Karnataka",
            "city": "Bengaluru",
            "zip": "560001",
        }
        payload.update(overrides)
        return payload

    def test_draft_with_only_identity_fields_succeeds(self):
        resp = self.client.post(
            "/company-onboarding/create/",
            {**self._identity_payload(), "action": "draft"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_next_blocks_on_missing_state_and_contact(self):
        resp = self.client.post(
            "/company-onboarding/create/",
            {
                **self._identity_payload(),
                "legal_name": "Acme Pvt Ltd",
                "tax_country": "INDIA",
                "pan": "ABCDE1234F",
                "currency": "INR",
                "action": "next",
            },
        )
        # No state/POC rows submitted -> strict validation blocks, stays on
        # the page (200), doesn't redirect to step 2.
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Place of Work")

    def _create_company_via_draft(self):
        resp = self.client.post(
            "/company-onboarding/create/",
            {**self._identity_payload(), "action": "draft"},
        )
        company_id = resp["Location"].split("/")[-3]
        return int(company_id)

    def test_back_never_blocks_even_with_invalid_step1_data(self):
        company_id = self._create_company_via_draft()
        resp = self.client.post(
            f"/company-onboarding/{company_id}/step-1/",
            {
                **self._identity_payload(),
                "tax_country": "INDIA",  # PAN deliberately omitted
                "action": "back",
            },
        )
        self.assertEqual(resp.status_code, 302)

    def test_full_wizard_reaches_active(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        company_id = self._create_company_via_draft()

        pdf = SimpleUploadedFile("msa.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        resp = self.client.post(
            f"/company-onboarding/{company_id}/step-1/",
            {
                **self._identity_payload(),
                "legal_name": "Acme Pvt Ltd",
                "tax_country": "INDIA",
                "pan": "ABCDE1234F",
                "invoice_cycle": "MONTHLY",
                "account_number": "1234567890",
                "bank_name": "Test Bank",
                "ifsc_swift": "TEST0001234",
                "currency": "INR",
                "msa_reference_number": "MSA-001",
                "start_date": "2026-01-01",
                "billing_model": "PER_HEAD",
                "billing_value": "500",
                "msa_document": pdf,
                "state1-row_id": "",
                "state1-state": str(self.maharashtra_state.pk),
                "state1-gstin": "",
                "poc1-row_id": "",
                "poc1-designation": "HR Head",
                "poc1-name": "Jane Doe",
                "poc1-email": "jane@acme.test",
                "poc1-mobile": "9999999999",
                "action": "next",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], f"/company-onboarding/{company_id}/step-2/")

        resp = self.client.post(
            f"/company-onboarding/{company_id}/step-2/",
            {
                "signatory1-row_id": "",
                "signatory1-signatory_type": "VENTURA",
                "signatory1-name": "Som Naskar",
                "signatory1-designation": "Director",
                "signatory1-email": "som@ventura.test",
                "signatory1-is_enabled": "on",
                "action": "next",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], f"/company-onboarding/{company_id}/step-3/")

        # Step 3 completeness (documents/branding) explicitly not required
        # for Active.
        resp = self.client.post(
            f"/company-onboarding/{company_id}/step-3/", {"action": "mark_active"}
        )
        self.assertEqual(resp.status_code, 302)

        from base.models import Company

        company = Company.objects.get(pk=company_id)
        self.assertEqual(company.status, "ACTIVE")

    def test_mark_active_reblocks_when_a_required_field_is_cleared_after_next(self):
        """
        Mark-as-Active is an independent re-check, not a "Next already
        passed" shortcut — clearing a required field directly (bypassing
        the wizard) must still block it.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        company_id = self._create_company_via_draft()
        pdf = SimpleUploadedFile("msa.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        self.client.post(
            f"/company-onboarding/{company_id}/step-1/",
            {
                **self._identity_payload(),
                "legal_name": "Acme Pvt Ltd",
                "tax_country": "INDIA",
                "pan": "ABCDE1234F",
                "invoice_cycle": "MONTHLY",
                "account_number": "1234567890",
                "bank_name": "Test Bank",
                "ifsc_swift": "TEST0001234",
                "currency": "INR",
                "msa_reference_number": "MSA-001",
                "start_date": "2026-01-01",
                "billing_model": "PER_HEAD",
                "billing_value": "500",
                "msa_document": pdf,
                "state1-row_id": "",
                "state1-state": str(self.maharashtra_state.pk),
                "state1-gstin": "",
                "poc1-row_id": "",
                "poc1-designation": "HR Head",
                "poc1-name": "Jane Doe",
                "poc1-email": "jane@acme.test",
                "poc1-mobile": "9999999999",
                "action": "next",
            },
        )
        self.client.post(
            f"/company-onboarding/{company_id}/step-2/",
            {
                "signatory1-row_id": "",
                "signatory1-signatory_type": "VENTURA",
                "signatory1-name": "Som Naskar",
                "signatory1-designation": "Director",
                "signatory1-email": "som@ventura.test",
                "signatory1-is_enabled": "on",
                "action": "next",
            },
        )

        from base.models import Company

        company = Company.objects.get(pk=company_id)
        company.legal_name = ""
        company.save(update_fields=["legal_name"])

        resp = self.client.post(
            f"/company-onboarding/{company_id}/step-3/", {"action": "mark_active"}
        )
        self.assertEqual(resp.status_code, 200)
        company.refresh_from_db()
        self.assertNotEqual(company.status, "ACTIVE")

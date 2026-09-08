from django.test import TestCase

from horilla.horilla_middlewares import _thread_locals
from horilla.testkit import (
    CompanyFilterTestMixin,
    make_company,
    make_employee,
    make_user,
)


class _ThreadLocalCleanupMixin:
    """
    HorillaModel.save() reads _thread_locals.request.user to auto-populate
    created_by — a plain threading.local, not reset by TestCase's per-test
    transaction rollback. Without this, a request made via self.client
    would leak a (soon rolled-back) user reference into the NEXT test's
    factory calls, causing a created_by FK violation there instead of here.
    Combined with CompanyFilterTestMixin, which resets the separate
    selected-company contextvar for the same class of cross-test-leak
    reason — company_onboarding's own models don't use
    HorillaCompanyManager (see models.py's Architecture note), but other
    company-scoped models elsewhere in the app still do.
    """

    def tearDown(self):
        _thread_locals.request = None
        super().tearDown()


class StatusTransitionTests(_ThreadLocalCleanupMixin, CompanyFilterTestMixin, TestCase):
    def setUp(self):
        # login_required requires a linked Employee, not just
        # is_authenticated — see test_wizard_flow.py's setUp for why.
        self.admin = make_user("ventura_admin", is_superuser=True)
        self.company = make_company(status="ACTIVE")
        make_employee(
            company=make_company("Ventura HQ"),
            email="ventura_admin@test.horilla",
            user=self.admin,
        )
        self.client.force_login(self.admin)
        # See test_wizard_flow.py's setUp for why this is needed.
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def test_put_on_hold_only_from_active(self):
        resp = self.client.post(f"/company-onboarding/{self.company.pk}/put-on-hold/")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ON_HOLD")

        # Already on_hold — second attempt should be a no-op, not error.
        resp = self.client.post(f"/company-onboarding/{self.company.pk}/put-on-hold/")
        self.assertEqual(resp.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ON_HOLD")

    def test_resume_only_from_on_hold(self):
        self.client.post(f"/company-onboarding/{self.company.pk}/put-on-hold/")
        self.client.post(f"/company-onboarding/{self.company.pk}/resume/")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ACTIVE")

    def _full_checklist(self):
        return {
            field: "on"
            for field in [
                "invoices_reconciled",
                "advances_collected",
                "employees_transferred_or_terminated",
                "compliances_closed",
                "employees_removed_from_insurance",
                "employees_deactivated_from_hrms",
                "data_handed_over",
            ]
        }

    def test_deactivate_blocks_without_full_checklist(self):
        payload = {"reason": "test"}
        payload.update(self._full_checklist())
        del payload["compliances_closed"]  # one item missing

        self.client.post(f"/company-onboarding/{self.company.pk}/deactivate/", payload)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ACTIVE")

    def test_deactivate_blocks_without_reason(self):
        payload = self._full_checklist()
        self.client.post(f"/company-onboarding/{self.company.pk}/deactivate/", payload)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ACTIVE")

    def test_deactivate_succeeds_and_creates_record(self):
        from company_onboarding.models import CompanyDeactivationRecord

        payload = {"reason": "Client churned"}
        payload.update(self._full_checklist())
        self.client.post(f"/company-onboarding/{self.company.pk}/deactivate/", payload)

        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "DEACTIVATED")
        record = CompanyDeactivationRecord.objects.get(company=self.company)
        self.assertEqual(record.reason, "Client churned")
        self.assertTrue(record.checklist_complete())
        self.assertEqual(record.confirmed_by, self.admin)

    def test_reinstate_only_from_deactivated_no_pan_retype(self):
        self.company.pan = "ABCDE1234F"
        self.company.tax_country = "INDIA"
        self.company.save()

        payload = {"reason": "Client churned"}
        payload.update(self._full_checklist())
        self.client.post(f"/company-onboarding/{self.company.pk}/deactivate/", payload)

        # No PAN retyping required at all — just the reinstate POST.
        resp = self.client.post(f"/company-onboarding/{self.company.pk}/reinstate/")
        self.assertEqual(resp.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ACTIVE")
        self.assertEqual(self.company.pan, "ABCDE1234F")


class VenturaHRPermissionTests(_ThreadLocalCleanupMixin, CompanyFilterTestMixin, TestCase):
    """Ventura HR can touch branding/documents but not status/core fields."""

    def setUp(self):
        from base.models import CompanyGroupAssignment
        from django.contrib.auth.models import Group

        self.company = make_company(status="ACTIVE")
        self.hr_user = make_user("ventura_hr")
        make_employee(
            company=make_company("Ventura HQ"),
            email="ventura_hr@test.horilla",
            user=self.hr_user,
        )
        hr_group = Group.objects.get(name="Ventura HR")
        # base.auth_backends.CompanyScopedBackend resolves group
        # permissions through CompanyGroupAssignment specifically (scoped
        # to a company), not the plain user.groups M2M — that plain add()
        # alone is what CompanyGroupAssignment.sync_user_group_membership
        # keeps in sync as a side effect, not the actual permission source.
        CompanyGroupAssignment.objects.create(
            user=self.hr_user, company=self.company, group=hr_group
        )
        self.hr_user.groups.add(hr_group)
        self.client.force_login(self.hr_user)
        # CompanyScopedBackend._resolve_company_id scopes permission
        # resolution to the SELECTED company. Unlike the superuser tests
        # (test_wizard_flow.py), "all" doesn't stick for a non-superuser
        # here — base.middleware.CompanyMiddleware._clamp_to_allowed only
        # preserves "all" mode when the user holds 2+ CompanyGroupAssignments;
        # with just the one (above), it clamps straight back down to their
        # own home company ("Ventura HQ"), ignoring "all" entirely. Selecting
        # self.company directly (which IS in their allowed set, via the
        # assignment) is what actually sticks — also more realistic, since a
        # single-company HR grant has no reason to need "all" mode.
        session = self.client.session
        session["selected_company"] = str(self.company.id)
        session.save()

    def test_hr_cannot_put_on_hold(self):
        # This codebase's permission_required doesn't return 403 — it
        # redirects (handle_no_permission), so the real assertion is that
        # the status genuinely didn't change, not a specific status code.
        self.client.post(f"/company-onboarding/{self.company.pk}/put-on-hold/")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "ACTIVE")

    def test_hr_cannot_edit_step1(self):
        resp = self.client.get(f"/company-onboarding/{self.company.pk}/step-1/")
        self.assertEqual(resp.status_code, 302)

    def test_hr_can_upload_branded_template(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        pdf = SimpleUploadedFile("offer.pdf", b"fake", content_type="application/pdf")
        resp = self.client.post(
            f"/company-onboarding/{self.company.pk}/step-3/",
            {
                "action": "upload_template",
                "template_type": "OFFER_LETTER",
                "template_file": pdf,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            self.company.branded_templates.filter(template_type="OFFER_LETTER").exists()
        )

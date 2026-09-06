"""
EmailLog must not persist credentials, and must be company-scoped.

ConfiguredEmailBackend logs every outbound mail body. send_otp puts the literal
two-factor code in that body and the reset mails carry single-use links, so both
were landing in a database table in cleartext. Separately, EmailLog had a
company_id FK that nothing populated and a plain Manager(), while the mail-log
views filter only on recipient address.
"""

from django.test import TestCase, override_settings

from base.email_redaction import REDACTED, redact_credential_body
from base.models import Company, EmailLog
from horilla.horilla_middlewares import set_selected_company


class RedactionTests(TestCase):
    def test_otp_subject_drops_the_whole_body(self):
        # Wholesale, not pattern-matched: partial redaction of an unknown
        # template is how secrets survive.
        self.assertEqual(
            redact_credential_body("Your OTP Code", "Your OTP code is 483920"),
            REDACTED,
        )

    def test_password_reset_subject_drops_the_body(self):
        self.assertEqual(
            redact_credential_body(
                "Password reset on Horilla", "Follow this link: /reset/abc/def/"
            ),
            REDACTED,
        )

    def test_inline_code_is_redacted_when_the_subject_is_innocuous(self):
        result = redact_credential_body("Welcome aboard", "Your code is 998877")

        self.assertNotIn("998877", result)
        self.assertIn(REDACTED, result)

    def test_reset_link_token_is_redacted(self):
        result = redact_credential_body(
            "Account notice", "Visit /reset/MTIz/set-password-token/ to continue"
        )

        self.assertNotIn("set-password-token", result)

    def test_ordinary_mail_is_left_intact(self):
        body = "Your leave request for 3 May was approved by Priya."

        # Over-redaction would make the mail log useless for support.
        self.assertEqual(redact_credential_body("Leave approved", body), body)

    def test_empty_body_is_handled(self):
        self.assertEqual(redact_credential_body("Anything", ""), "")
        self.assertEqual(redact_credential_body(None, None), "")


class EmailLogScopingTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(company="Alpha", hq=True)
        self.company_b = Company.objects.create(company="Beta")
        self.addCleanup(set_selected_company, None)

        for company in (self.company_a, self.company_b):
            EmailLog.objects.create(
                subject="Leave approved",
                from_email="hr@example.com",
                to="someone@example.com",
                body="body",
                status="sent",
                company_id=company,
            )

    def test_rows_are_scoped_to_the_selected_company(self):
        set_selected_company(str(self.company_a.id))

        rows = EmailLog.objects.all()

        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().company_id, self.company_a)

    def test_other_tenants_rows_are_not_visible(self):
        set_selected_company(str(self.company_b.id))

        subjects = list(EmailLog.objects.values_list("company_id", flat=True))

        self.assertNotIn(self.company_a.id, subjects)


class LegacyNullCompanyRowsTests(TestCase):
    """
    Rows written before company_id was populated are NULL.

    HorillaCompanyManager treats a NULL company as visible to everyone
    (Q(path__isnull=True)), which is deliberate for shared configuration but
    means historical mail-log rows stay cross-tenant readable. Asserted here so
    the behaviour is a documented decision rather than a surprise, and so a
    future backfill has a test to flip.
    """

    def setUp(self):
        self.company = Company.objects.create(company="Alpha", hq=True)
        self.addCleanup(set_selected_company, None)
        EmailLog.objects.create(
            subject="Historical mail",
            from_email="hr@example.com",
            to="someone@example.com",
            body="body",
            status="sent",
            company_id=None,
        )

    def test_null_company_rows_remain_visible(self):
        set_selected_company(str(self.company.id))

        self.assertEqual(EmailLog.objects.filter(subject="Historical mail").count(), 1)

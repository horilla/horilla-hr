"""
The candidate login is limited, per email and per client address.

It checks its password itself, so django-axes and the failed-login handler
never see it. Without a limit an emailed password could be guessed without end.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from horilla.testkit.factories import make_candidate, make_company, make_recruitment
from recruitment.views.views import (
    CANDIDATE_LOGIN_ADDRESS_LIMIT,
    CANDIDATE_LOGIN_EMAIL_LIMIT,
)

PASSWORD = "Right-Pass-123"


@override_settings(HORILLA_TRUSTED_PROXIES=[])
class CandidateLoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        recruitment = make_recruitment(company=make_company("Hiring Co"))
        self.candidate = make_candidate(
            recruitment=recruitment, email="applicant@test.horilla"
        )
        self.candidate.issue_portal_password(PASSWORD)
        self.url = reverse("candidate-login")

    def _login(self, email, password, address="198.51.100.7"):
        return self.client.post(
            self.url, {"email": email, "password": password}, REMOTE_ADDR=address
        )

    def test_the_right_password_logs_in(self):
        response = self._login("applicant@test.horilla", PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["candidate_id"], self.candidate.pk)

    def test_after_the_limit_even_the_right_password_is_refused(self):
        for _ in range(CANDIDATE_LOGIN_EMAIL_LIMIT):
            self.assertEqual(
                self._login("applicant@test.horilla", "wrong").status_code, 200
            )
        response = self._login("applicant@test.horilla", PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("candidate_id", self.client.session)

    def test_the_email_limit_holds_across_addresses(self):
        for i in range(CANDIDATE_LOGIN_EMAIL_LIMIT):
            self._login("applicant@test.horilla", "wrong", address=f"203.0.113.{i + 1}")
        response = self._login(
            "applicant@test.horilla", PASSWORD, address="203.0.113.99"
        )
        self.assertEqual(response.status_code, 429)

    def test_the_email_limit_ignores_letter_case(self):
        for _ in range(CANDIDATE_LOGIN_EMAIL_LIMIT):
            self._login("Applicant@Test.Horilla", "wrong")
        self.assertEqual(
            self._login("applicant@test.horilla", PASSWORD).status_code, 429
        )

    def test_a_success_resets_the_email_count(self):
        for _ in range(CANDIDATE_LOGIN_EMAIL_LIMIT - 1):
            self._login("applicant@test.horilla", "wrong")
        self.assertEqual(
            self._login("applicant@test.horilla", PASSWORD).status_code, 302
        )
        self.client.logout()
        for _ in range(CANDIDATE_LOGIN_EMAIL_LIMIT - 1):
            self._login("applicant@test.horilla", "wrong")
        self.assertEqual(
            self._login("applicant@test.horilla", PASSWORD).status_code, 302
        )

    def test_one_address_trying_many_emails_is_limited(self):
        for i in range(CANDIDATE_LOGIN_ADDRESS_LIMIT):
            self._login(f"someone{i}@test.horilla", "wrong")
        self.assertEqual(
            self._login("applicant@test.horilla", PASSWORD).status_code, 429
        )

    def test_a_few_failures_from_a_shared_address_do_not_lock_others_out(self):
        for i in range(CANDIDATE_LOGIN_EMAIL_LIMIT):
            self._login(f"colleague{i}@test.horilla", "wrong")
        self.assertEqual(
            self._login("applicant@test.horilla", PASSWORD).status_code, 302
        )

    def test_the_session_key_changes_on_login(self):
        self.client.get(self.url)
        self.client.session.save()
        before = self.client.session.session_key
        self._login("applicant@test.horilla", PASSWORD)
        self.assertNotEqual(self.client.session.session_key, before)

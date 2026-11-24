"""Two-factor sign-in for an employee without an email.

The two-factor code goes by email. Someone without an address cannot get
one, so they stay on the two-factor page, which says why, rather than being
sent a code that goes nowhere.
"""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from base.models import DynamicEmailConfiguration
from horilla.testkit import make_company, make_employee, make_user

NO_EMAIL_MESSAGE = "Two-factor sign-in needs an email address on your profile"


@override_settings(TWO_FACTORS_AUTHENTICATION=True)
class TwoFactorWithoutEmailTests(TestCase):
    def setUp(self):
        company = make_company("Co")
        DynamicEmailConfiguration.objects.create(
            host="localhost",
            port=25,
            from_email="hr@test.horilla",
            display_name="HR",
            is_primary=True,
        )
        self.user = make_user("sam")
        make_employee(company=company, email="", user=self.user)
        self.client.force_login(self.user)

    def test_the_app_stays_behind_the_two_factor_page(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/two-factor", fetch_redirect_response=False)

    def test_the_two_factor_page_says_an_email_is_needed_and_sends_nothing(self):
        response = self.client.get("/two-factor/")
        self.assertContains(response, NO_EMAIL_MESSAGE)
        self.assertIsNone(self.client.session.get("otp_code"))
        self.assertEqual(mail.outbox, [])

    def test_asking_for_a_code_sends_nothing(self):
        self.client.post("/send-otp/")
        self.assertIsNone(self.client.session.get("otp_code"))
        self.assertEqual(mail.outbox, [])

    def test_posting_a_code_does_not_sign_in(self):
        response = self.client.post("/two-factor/", {"otp": "123456"})
        self.assertContains(response, NO_EMAIL_MESSAGE)
        self.assertFalse(self.client.session.get("otp_code_verified", False))

    def test_an_employee_with_an_email_is_still_sent_a_code(self):
        user = make_user("alex")
        make_employee(
            company=make_company("Other"), email="alex@test.horilla", user=user
        )
        self.client.force_login(user)
        with patch("base.views.threading.Thread") as thread:
            response = self.client.get("/two-factor/")
        thread.assert_called_once()
        self.assertNotContains(response, NO_EMAIL_MESSAGE)
        self.assertIsNotNone(self.client.session.get("otp_code"))

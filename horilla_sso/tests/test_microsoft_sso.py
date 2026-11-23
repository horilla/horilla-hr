"""Microsoft sign-in: the token checks, the employee match, the callback and the settings page."""

import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from horilla_sso import crypto, methods
from horilla_sso.models import MicrosoftSSOSettings, SSOLoginSettings

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_config(**overrides):
    config = MicrosoftSSOSettings(
        is_enabled=True,
        tenant_id=TENANT,
        client_id=CLIENT,
        allowed_domains="",
        **overrides,
    )
    config.client_secret = "s3cret"
    config.save()
    return config


def id_token(nonce, **claims):
    body = {
        "aud": CLIENT,
        "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
        "tid": TENANT,
        "exp": int(time.time()) + 600,
        "nonce": nonce,
        "email": "ada@contoso.test",
    }
    body.update(claims)
    return jwt.encode(body, KEY, algorithm="RS256")


def signed_by_us():
    return mock.patch.object(methods, "_signing_key", return_value=KEY.public_key())


class TokenTests(TestCase):
    def setUp(self):
        self.config = make_config()

    def check(self, token, nonce="n1"):
        with signed_by_us():
            return methods.validate_id_token(self.config, token, nonce)

    def test_valid_token_gives_claims(self):
        self.assertEqual(self.check(id_token("n1"))["email"], "ada@contoso.test")

    def test_wrong_audience_rejected(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token("n1", aud="someone-else"))

    def test_wrong_nonce_rejected(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token("other"))

    def test_expired_rejected(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token("n1", exp=int(time.time()) - 3600))

    def test_other_signer_rejected(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "tid": TENANT,
            "exp": int(time.time()) + 600,
            "nonce": "n1",
        }
        with self.assertRaises(methods.SSOError):
            self.check(jwt.encode(body, other, algorithm="RS256"))

    def test_other_directory_rejected_for_a_single_tenant_app(self):
        other = "99999999-2222-3333-4444-555555555555"
        with self.assertRaises(methods.SSOError):
            self.check(
                id_token("n1", tid=other, iss=f"{methods.AUTHORITY}/{other}/v2.0")
            )

    def test_issuer_must_match_the_token_tenant(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token("n1", iss="https://evil.test/x/v2.0"))

    def test_organizations_app_accepts_any_directory(self):
        self.config.tenant_id = "organizations"
        other = "99999999-2222-3333-4444-555555555555"
        claims = self.check(
            id_token("n1", tid=other, iss=f"{methods.AUTHORITY}/{other}/v2.0")
        )
        self.assertEqual(claims["tid"], other)

    def test_authorization_url_carries_state_and_nonce(self):
        url, state, nonce = methods.build_authorization_url(self.config, "http://x/cb/")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["state"], [state])
        self.assertEqual(query["nonce"], [nonce])
        self.assertEqual(query["client_id"], [CLIENT])
        self.assertEqual(query["redirect_uri"], ["http://x/cb/"])


class EmployeeMatchTests(TestCase):
    def setUp(self):
        self.company = make_company("Match Co")
        self.employee = make_employee(
            company=self.company, email="ada@contoso.test", first_name="Ada"
        )

    def test_matches_email_ignoring_case(self):
        found = methods.find_employee({"email": "ADA@Contoso.test"})
        self.assertEqual(found, self.employee)

    def test_matches_work_email(self):
        other = make_employee(
            company=self.company, email="grace.home@x.test", first_name="Grace"
        )
        other.employee_work_info.email = "grace@contoso.test"
        other.employee_work_info.save()
        self.assertEqual(
            methods.find_employee({"preferred_username": "grace@contoso.test"}), other
        )

    def test_unknown_email_gives_none(self):
        self.assertIsNone(methods.find_employee({"email": "nobody@contoso.test"}))

    def test_domain_filter(self):
        config = make_config()
        config.allowed_domains = "contoso.test, @fabrikam.test"
        self.assertTrue(methods.domain_allowed(config, {"email": "a@fabrikam.test"}))
        self.assertFalse(methods.domain_allowed(config, {"email": "a@evil.test"}))
        config.allowed_domains = ""
        self.assertTrue(methods.domain_allowed(config, {"email": "a@evil.test"}))


class CallbackTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.config = make_config()
        self.company = make_company("Sso Co")
        self.user = make_user("ada", password="x")
        self.employee = make_employee(
            company=self.company,
            email="ada@contoso.test",
            first_name="Ada",
            user=self.user,
        )

    def start(self, **query):
        response = self.client.get(reverse("microsoft-sso-login"), query)
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response["Location"]).query)
        return params["state"][0], params["nonce"][0]

    def finish(self, token, state, code="abc"):
        with mock.patch.object(
            methods, "exchange_code", return_value=token
        ), signed_by_us():
            return self.client.get(
                reverse("microsoft-sso-callback"), {"code": code, "state": state}
            )

    def test_success_logs_in_and_lands_on_next(self):
        state, nonce = self.start(next="/employee/")
        response = self.finish(id_token(nonce), state)
        self.assertRedirects(response, "/employee/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_success_clears_the_forced_password_change(self):
        self.user.is_new_employee = True
        self.user.save()
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_new_employee)

    def test_success_marks_two_factor_as_done(self):
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        self.assertTrue(self.client.session["otp_code_verified"])

    def test_outside_redirect_is_refused(self):
        state, nonce = self.start(next="https://evil.test/")
        response = self.finish(id_token(nonce), state)
        self.assertEqual(response.url, "/")

    def assert_refused(self, response):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_state_refused(self):
        _, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce), "forged"))

    def test_callback_without_a_started_sign_in_refused(self):
        self.assert_refused(self.finish(id_token("n"), "anything"))

    def test_microsoft_error_refused_and_its_reason_shown(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"),
            {
                "error": "access_denied",
                "error_description": "AADSTS65001: Consent needed",
                "state": state,
            },
        )
        self.assert_refused(response)
        self.assertIn(
            "AADSTS65001", [str(m) for m in get_messages(response.wsgi_request)][0]
        )

    def test_microsoft_error_reason_hidden_without_the_started_state(self):
        self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"),
            {
                "error": "access_denied",
                "error_description": "Call us on 555",
                "state": "forged",
            },
        )
        self.assert_refused(response)
        self.assertNotIn(
            "555", [str(m) for m in get_messages(response.wsgi_request)][0]
        )

    def test_unknown_employee_refused(self):
        state, nonce = self.start()
        self.assert_refused(
            self.finish(id_token(nonce, email="stranger@contoso.test"), state)
        )

    def test_archived_employee_refused(self):
        self.employee.is_active = False
        self.employee.save()
        state, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce), state))

    def test_disallowed_domain_refused(self):
        self.config.allowed_domains = "fabrikam.test"
        self.config.save()
        state, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce), state))

    def test_state_is_single_use(self):
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        self.client.logout()
        self.assert_refused(self.finish(id_token(nonce), state))

    def test_start_refused_when_not_enabled(self):
        self.config.is_enabled = False
        self.config.save()
        self.assertRedirects(
            self.client.get(reverse("microsoft-sso-login")),
            reverse("login"),
            fetch_redirect_response=False,
        )


class LoginPageTests(TestCase):
    def test_no_button_without_configuration(self):
        page = Client().get(reverse("login"))
        self.assertNotContains(page, reverse("microsoft-sso-login"))

    def test_button_shown_when_ready(self):
        make_config()
        page = Client().get(reverse("login"))
        self.assertContains(page, reverse("microsoft-sso-login"))
        self.assertNotContains(page, "showPasswordLogin")

    def test_password_form_hidden_with_a_link_to_show_it(self):
        make_config()
        SSOLoginSettings.objects.create(hide_password_form=True)
        page = Client().get(reverse("login"))
        self.assertContains(page, "showPasswordLogin")
        self.assertContains(page, 'id="passwordLoginForm"')
        self.assertRegex(page.content.decode(), r'id="passwordLoginForm"[^>]*hidden')

    def test_no_button_when_switched_off(self):
        make_config().delete()
        config = make_config()
        config.is_enabled = False
        config.save()
        self.assertNotContains(
            Client().get(reverse("login")), reverse("microsoft-sso-login")
        )


class SettingsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = make_company("Settings Co")
        self.admin = make_user("root", password="x", is_superuser=True)
        make_employee(company=self.company, email="root@x.test", user=self.admin)

    def test_secret_is_encrypted_at_rest(self):
        self.assertEqual(crypto.decrypt(crypto.encrypt("abc")), "abc")
        self.assertNotIn("abc", crypto.encrypt("abc"))

    def test_page_is_for_superusers_only(self):
        user = make_user("plain", password="x")
        make_employee(company=self.company, email="plain@x.test", user=user)
        self.client.force_login(user)
        self.assertNotEqual(
            self.client.get(reverse("microsoft-sso-settings")).status_code, 200
        )

    def post(self, **data):
        self.client.force_login(self.admin)
        payload = {
            "tenant_id": TENANT,
            "client_id": CLIENT,
            "client_secret": "s3cret",
            "is_enabled": "on",
        }
        payload.update(data)
        return self.client.post(reverse("microsoft-sso-settings"), payload)

    def test_saving_stores_the_secret_encrypted_and_fills_it_back_in(self):
        self.post()
        config = MicrosoftSSOSettings.current()
        self.assertEqual(config.client_secret, "s3cret")
        self.assertNotIn("s3cret", config.client_secret_encrypted)
        page = self.client.get(reverse("microsoft-sso-settings"))
        self.assertEqual(page.status_code, 200)
        self.assertRegex(
            page.content.decode(), r'name="client_secret"[^>]*value="s3cret"'
        )
        self.assertContains(page, reverse("microsoft-sso-callback"))

    def test_blank_secret_keeps_the_saved_one(self):
        self.post()
        self.post(client_secret="", client_id="ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee")
        config = MicrosoftSSOSettings.current()
        self.assertEqual(
            (config.client_id, config.client_secret),
            ("ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee", "s3cret"),
        )

    def test_cannot_enable_without_a_secret(self):
        self.post(client_secret="")
        self.assertIsNone(MicrosoftSSOSettings.current())

"""Google sign-in: the token and Workspace rules, the callback, the login page and the settings page."""

import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.messages import get_messages
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from horilla_sso import methods
from horilla_sso.models import GoogleSSOSettings, MicrosoftSSOSettings, SSOLoginSettings
from horilla_sso.tests.test_microsoft_sso import make_config as make_microsoft_config

CLIENT = "123456789012-abcdef123456.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CERTS = "https://www.googleapis.com/oauth2/v3/certs"


def make_config(**overrides):
    values = {
        "is_enabled": True,
        "client_id": CLIENT,
        "allowed_domains": "contoso.test",
    }
    values.update(overrides)
    config = GoogleSSOSettings(**values)
    config.client_secret = "GOCSPX-s3cret"
    config.save()
    return config


def id_token(nonce, **claims):
    body = {
        "aud": CLIENT,
        "iss": "https://accounts.google.com",
        "exp": int(time.time()) + 600,
        "nonce": nonce,
        "email": "ada@contoso.test",
        "email_verified": True,
        "hd": "contoso.test",
    }
    body.update(claims)
    return jwt.encode(
        {k: v for k, v in body.items() if v is not None}, KEY, algorithm="RS256"
    )


def signed_by_us():
    return mock.patch.object(methods, "_signing_key", return_value=KEY.public_key())


class TokenTests(TestCase):
    def setUp(self):
        self.config = make_config()

    def check(self, token, nonce="n1"):
        with signed_by_us():
            return methods.validate_id_token(self.config, token, nonce)

    def refused(self, token, nonce="n1"):
        with self.assertRaises(methods.SSOError):
            self.check(token, nonce)

    def test_valid_token_gives_claims(self):
        self.assertEqual(self.check(id_token("n1"))["email"], "ada@contoso.test")

    def test_both_google_issuer_spellings_accepted(self):
        self.check(id_token("n1", iss="accounts.google.com"))
        self.check(id_token("n1", iss="https://accounts.google.com"))

    def test_other_issuer_refused(self):
        self.refused(id_token("n1", iss="https://accounts.evil.test"))
        self.refused(id_token("n1", iss="https://login.microsoftonline.com/x/v2.0"))

    def test_wrong_audience_refused(self):
        self.refused(id_token("n1", aud="999-other.apps.googleusercontent.com"))

    def test_wrong_nonce_refused(self):
        self.refused(id_token("n1"), nonce="n2")

    def test_missing_nonce_refused(self):
        self.refused(id_token("n1"), nonce="")

    def test_expired_refused(self):
        self.refused(id_token("n1", exp=int(time.time()) - 3600))

    def test_other_signer_refused(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with mock.patch.object(
            methods, "_signing_key", return_value=other.public_key()
        ):
            with self.assertRaises(methods.SSOError):
                methods.validate_id_token(self.config, id_token("n1"), "n1")

    def test_unsigned_token_refused(self):
        forged = jwt.encode(
            {
                "aud": CLIENT,
                "iss": "https://accounts.google.com",
                "exp": int(time.time()) + 600,
            },
            None,
            algorithm="none",
        )
        self.refused(forged)

    def test_unverified_email_refused(self):
        self.refused(id_token("n1", email_verified=False))

    def test_missing_email_verified_refused(self):
        self.refused(id_token("n1", email_verified=None))

    def test_signing_keys_come_from_google(self):
        with mock.patch.object(
            methods, "_signing_key", return_value=KEY.public_key()
        ) as key:
            methods.validate_id_token(self.config, id_token("n1"), "n1")
        self.assertEqual(key.call_args.args[1], CERTS)

    def test_authorization_url_carries_state_nonce_and_a_domain_hint(self):
        url, state, nonce = methods.build_authorization_url(self.config, "http://x/cb/")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "https://accounts.google.com/o/oauth2/v2/auth",
        )
        self.assertEqual(
            (
                query["state"][0],
                query["nonce"][0],
                query["client_id"][0],
                query["hd"][0],
            ),
            (state, nonce, CLIENT, "contoso.test"),
        )
        self.assertEqual(query["redirect_uri"][0], "http://x/cb/")

    def test_no_domain_hint_with_several_domains(self):
        self.config.allowed_domains = "contoso.test, fabrikam.test"
        url, _state, _nonce = methods.build_authorization_url(
            self.config, "http://x/cb/"
        )
        self.assertNotIn("hd", parse_qs(urlparse(url).query))


class WorkspaceRuleTests(TestCase):
    def setUp(self):
        self.config = make_config()
        self.company = make_company("Rule Co")
        self.employee = make_employee(
            company=self.company, email="ada@contoso.test", first_name="Ada"
        )

    def allowed(self, **claims):
        body = {
            "email": "ada@contoso.test",
            "email_verified": True,
            "hd": "contoso.test",
        }
        body.update(claims)
        return methods.domain_allowed(self.config, body)

    def test_workspace_account_of_an_allowed_domain_passes(self):
        self.assertTrue(self.allowed())

    def test_hosted_domain_is_compared_ignoring_case(self):
        self.assertTrue(self.allowed(hd="Contoso.Test"))

    def test_personal_gmail_without_hd_refused(self):
        self.assertFalse(self.allowed(email="ada@contoso.test", hd=None))

    def test_a_gmail_address_that_looks_like_the_company_refused(self):
        self.assertFalse(self.allowed(email="ada@gmail.com", hd=None))

    def test_hd_of_another_domain_refused(self):
        self.assertFalse(self.allowed(hd="fabrikam.test"))

    def test_email_domain_must_match_hd(self):
        self.assertFalse(self.allowed(email="ada@fabrikam.test"))

    def test_unverified_email_refused(self):
        self.assertFalse(self.allowed(email_verified=False))

    def test_no_domains_means_nobody(self):
        self.config.allowed_domains = ""
        self.assertFalse(self.allowed())

    def test_only_the_email_claim_is_read(self):
        found = methods.find_employee(
            {
                "email_verified": True,
                "preferred_username": "ada@contoso.test",
                "upn": "ada@contoso.test",
            },
            provider="google",
        )
        self.assertIsNone(found)

    def test_matches_email_ignoring_case_and_work_email(self):
        claims = {"email": "ADA@Contoso.Test", "email_verified": True}
        self.assertEqual(
            methods.find_employee(claims, provider="google"), self.employee
        )

    def test_unverified_email_never_matches(self):
        claims = {"email": "ada@contoso.test", "email_verified": False}
        self.assertIsNone(methods.find_employee(claims, provider="google"))

    def test_two_employees_with_one_work_email_is_no_match(self):
        other = make_employee(
            company=self.company, email="grace@x.test", first_name="Grace"
        )
        for person in (self.employee, other):
            person.employee_work_info.email = "shared@contoso.test"
            person.employee_work_info.save()
        self.employee.email = "different@contoso.test"
        self.employee.save()
        self.assertIsNone(
            methods.find_employee(
                {"email": "shared@contoso.test", "email_verified": True},
                provider="google",
            )
        )


class ExchangeTests(TestCase):
    def setUp(self):
        self.config = make_config()

    def test_code_goes_to_google_without_a_microsoft_scope(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"id_token": "tok"}
        with mock.patch.object(methods.requests, "post", return_value=reply) as post:
            self.assertEqual(
                methods.exchange_code(self.config, "abc", "http://x/cb/"), "tok"
            )
        self.assertEqual(post.call_args.args[0], "https://oauth2.googleapis.com/token")
        self.assertNotIn("scope", post.call_args.kwargs["data"])
        self.assertEqual(
            post.call_args.kwargs["data"]["client_secret"], "GOCSPX-s3cret"
        )

    def test_google_unreachable_is_a_sign_in_error(self):
        with mock.patch.object(
            methods.requests, "post", side_effect=requests.Timeout("slow")
        ):
            with self.assertRaises(methods.SSOError) as raised:
                methods.exchange_code(self.config, "abc", "http://x/cb/")
        self.assertIn("Google", str(raised.exception))

    def test_refusal_from_google_is_a_sign_in_error(self):
        reply = mock.Mock(status_code=400)
        reply.json.return_value = {"error": "invalid_grant"}
        with mock.patch.object(methods.requests, "post", return_value=reply):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_non_json_reply_is_a_sign_in_error(self):
        reply = mock.Mock(status_code=200)
        reply.json.side_effect = ValueError("no json")
        with mock.patch.object(methods.requests, "post", return_value=reply):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")


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
        response = self.client.get(reverse("google-sso-login"), query)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://accounts.google.com/"))
        params = parse_qs(urlparse(response["Location"]).query)
        return params["state"][0], params["nonce"][0]

    def finish(self, token, state, code="abc"):
        with mock.patch.object(
            methods, "exchange_code", return_value=token
        ), signed_by_us():
            return self.client.get(
                reverse("google-sso-callback"), {"code": code, "state": state}
            )

    def assert_refused(self, response):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

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
        self.assertEqual(self.finish(id_token(nonce), state).url, "/")

    def test_wrong_state_refused(self):
        _, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce), "forged"))

    def test_non_ascii_state_is_refused_without_a_server_error(self):
        _, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce), "é✓"))

    def test_callback_without_a_started_sign_in_refused(self):
        self.assert_refused(self.finish(id_token("n"), "anything"))

    def test_callback_without_a_code_refused(self):
        state, _ = self.start()
        self.assert_refused(
            self.client.get(reverse("google-sso-callback"), {"state": state})
        )

    def test_state_is_single_use(self):
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        self.client.logout()
        self.assert_refused(self.finish(id_token(nonce), state))

    def test_google_error_refused_and_its_reason_shown(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("google-sso-callback"), {"error": "access_denied", "state": state}
        )
        self.assert_refused(response)
        self.assertIn(
            "access_denied", [str(m) for m in get_messages(response.wsgi_request)][0]
        )

    def test_google_error_reason_hidden_without_the_started_state(self):
        self.start()
        response = self.client.get(
            reverse("google-sso-callback"),
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

    def test_personal_gmail_refused(self):
        state, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce, hd=None), state))

    def test_other_workspace_refused(self):
        state, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce, hd="fabrikam.test"), state))

    def test_unverified_email_refused(self):
        state, nonce = self.start()
        self.assert_refused(self.finish(id_token(nonce, email_verified=False), state))

    def test_token_for_another_app_refused(self):
        state, nonce = self.start()
        self.assert_refused(
            self.finish(
                id_token(nonce, aud="999-other.apps.googleusercontent.com"), state
            )
        )

    def test_network_failure_refused_without_a_server_error(self):
        state, _ = self.start()
        with mock.patch.object(
            methods.requests, "post", side_effect=requests.ConnectionError("down")
        ):
            response = self.client.get(
                reverse("google-sso-callback"), {"code": "abc", "state": state}
            )
        self.assert_refused(response)

    def test_start_refused_when_not_enabled(self):
        self.config.is_enabled = False
        self.config.save()
        self.assertRedirects(
            self.client.get(reverse("google-sso-login")),
            reverse("login"),
            fetch_redirect_response=False,
        )

    def test_start_refused_without_a_domain(self):
        self.config.allowed_domains = ""
        self.config.save()
        self.assertRedirects(
            self.client.get(reverse("google-sso-login")),
            reverse("login"),
            fetch_redirect_response=False,
        )


class ProviderMixTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.google = make_config()
        self.microsoft = make_microsoft_config()

    def test_a_microsoft_start_cannot_finish_on_the_google_callback(self):
        response = self.client.get(reverse("microsoft-sso-login"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        reply = self.client.get(
            reverse("google-sso-callback"), {"code": "abc", "state": state}
        )
        self.assertRedirects(reply, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_google_start_cannot_finish_on_the_microsoft_callback(self):
        response = self.client.get(reverse("google-sso-login"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        with mock.patch.object(methods, "exchange_code") as exchange:
            reply = self.client.get(
                reverse("microsoft-sso-callback"), {"code": "abc", "state": state}
            )
        exchange.assert_not_called()
        self.assertRedirects(reply, reverse("login"), fetch_redirect_response=False)

    def test_a_mismatched_error_reply_shows_no_provider_text(self):
        response = self.client.get(reverse("microsoft-sso-login"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        reply = self.client.get(
            reverse("google-sso-callback"),
            {
                "error": "access_denied",
                "error_description": "Call us on 555",
                "state": state,
            },
        )
        self.assertNotIn("555", [str(m) for m in get_messages(reply.wsgi_request)][0])

    def test_each_provider_reads_its_own_settings(self):
        self.assertEqual(GoogleSSOSettings.current().client_id, CLIENT)
        self.assertNotEqual(MicrosoftSSOSettings.current().client_id, CLIENT)

    def test_unknown_provider_is_not_found(self):
        from horilla_sso import views

        request = mock.Mock()
        with self.assertRaises(Http404):
            views.sso_login(request, "github")


class LoginPageTests(TestCase):
    def test_no_google_button_without_configuration(self):
        self.assertNotContains(
            Client().get(reverse("login")), reverse("google-sso-login")
        )

    def test_google_button_shown_when_ready(self):
        make_config()
        page = Client().get(reverse("login"))
        self.assertContains(page, reverse("google-sso-login"))
        self.assertContains(page, "Sign In With Google")
        self.assertNotContains(page, reverse("microsoft-sso-login"))

    def test_both_buttons_shown_when_both_ready(self):
        make_config()
        make_microsoft_config()
        page = Client().get(reverse("login"))
        self.assertContains(page, reverse("google-sso-login"))
        self.assertContains(page, reverse("microsoft-sso-login"))

    def test_no_google_button_when_it_has_no_domain(self):
        make_config(allowed_domains="")
        self.assertNotContains(
            Client().get(reverse("login")), reverse("google-sso-login")
        )

    def test_no_google_button_when_switched_off(self):
        make_config(is_enabled=False)
        self.assertNotContains(
            Client().get(reverse("login")), reverse("google-sso-login")
        )

    def test_one_switch_hides_the_password_form_for_both(self):
        make_config()
        make_microsoft_config()
        SSOLoginSettings.objects.create(hide_password_form=True)
        page = Client().get(reverse("login"))
        self.assertContains(page, "showPasswordLogin")
        self.assertRegex(page.content.decode(), r'id="passwordLoginForm"[^>]*hidden')

    def test_hiding_is_ignored_when_no_provider_is_ready(self):
        SSOLoginSettings.objects.create(hide_password_form=True)
        page = Client().get(reverse("login"))
        self.assertNotContains(page, "showPasswordLogin")
        self.assertNotRegex(page.content.decode(), r'id="passwordLoginForm"[^>]*hidden')

    def test_next_is_carried_to_the_google_start(self):
        make_config()
        page = Client().get(reverse("login"), {"next": "/employee/"})
        self.assertContains(page, f'{reverse("google-sso-login")}?next=/employee/')


class SettingsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = make_company("Settings Co")
        self.admin = make_user("root", password="x", is_superuser=True)
        make_employee(company=self.company, email="root@x.test", user=self.admin)

    def post(self, **data):
        self.client.force_login(self.admin)
        payload = {
            "client_id": CLIENT,
            "client_secret": "GOCSPX-s3cret",
            "allowed_domains": "contoso.test",
            "is_enabled": "on",
        }
        payload.update(data)
        return self.client.post(reverse("google-sso-settings"), payload)

    def test_page_is_for_superusers_only(self):
        user = make_user("plain", password="x")
        make_employee(company=self.company, email="plain@x.test", user=user)
        self.client.force_login(user)
        self.assertNotEqual(
            self.client.get(reverse("google-sso-settings")).status_code, 200
        )

    def test_page_shows_the_google_redirect_uri(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("google-sso-settings"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, reverse("google-sso-callback"))
        self.assertContains(page, "Google Cloud Console")

    def test_saving_stores_the_secret_encrypted_and_fills_it_back_in(self):
        self.post()
        config = GoogleSSOSettings.current()
        self.assertEqual(config.client_secret, "GOCSPX-s3cret")
        self.assertNotIn("GOCSPX-s3cret", config.client_secret_encrypted)
        page = self.client.get(reverse("google-sso-settings"))
        self.assertRegex(
            page.content.decode(), r'name="client_secret"[^>]*value="GOCSPX-s3cret"'
        )

    def test_blank_secret_keeps_the_saved_one(self):
        self.post()
        self.post(
            client_secret="", client_id="999999999999-zzzzzz.apps.googleusercontent.com"
        )
        config = GoogleSSOSettings.current()
        self.assertEqual(
            (config.client_id, config.client_secret),
            ("999999999999-zzzzzz.apps.googleusercontent.com", "GOCSPX-s3cret"),
        )

    def test_cannot_enable_without_a_secret(self):
        self.post(client_secret="")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_cannot_enable_without_a_client_id(self):
        self.post(client_id="")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_cannot_enable_without_a_domain(self):
        self.post(allowed_domains="")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_can_save_switched_off_without_a_domain(self):
        self.post(allowed_domains="", is_enabled="")
        self.assertIsNotNone(GoogleSSOSettings.current())

    def test_client_id_of_the_wrong_shape_refused(self):
        self.post(client_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_secret_that_is_the_client_id_refused(self):
        self.post(client_secret=CLIENT)
        self.assertIsNone(GoogleSSOSettings.current())

    def test_secret_with_spaces_refused(self):
        self.post(client_secret="GOCSPX abc")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_email_instead_of_a_domain_refused(self):
        self.post(allowed_domains="ada@contoso.test")
        self.assertIsNone(GoogleSSOSettings.current())

    def test_domains_are_cleaned_and_deduplicated(self):
        self.post(allowed_domains=" @Contoso.Test; fabrikam.test,contoso.test ")
        self.assertEqual(
            GoogleSSOSettings.current().allowed_domains, "contoso.test, fabrikam.test"
        )

    def test_the_shared_switch_is_saved_once_for_everyone(self):
        self.post(hide_password_form="on")
        self.assertTrue(SSOLoginSettings.hides_password_form())
        self.post()
        self.assertFalse(SSOLoginSettings.hides_password_form())
        self.assertEqual(SSOLoginSettings.objects.count(), 1)

    def test_cannot_hide_the_password_form_with_no_provider_on(self):
        self.post(is_enabled="", hide_password_form="on")
        self.assertFalse(SSOLoginSettings.hides_password_form())

    def test_can_hide_the_password_form_when_microsoft_is_the_provider_on(self):
        make_microsoft_config()
        self.post(is_enabled="", hide_password_form="on")
        self.assertTrue(SSOLoginSettings.hides_password_form())

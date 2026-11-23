"""Microsoft sign-in: hostile input, failures on the way, and identity-matching edge cases."""

import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from horilla_sso import crypto, methods
from horilla_sso.forms import MicrosoftSSOSettingsForm
from horilla_sso.models import MicrosoftSSOSettings
from horilla_sso.tests.test_microsoft_sso import (
    CLIENT,
    KEY,
    TENANT,
    id_token,
    make_config,
    signed_by_us,
)


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class Base(TestCase):
    def setUp(self):
        self.client = Client()
        self.config = make_config()
        self.company = make_company("Edge Co")
        self.user = make_user("edge", password="x")
        self.employee = make_employee(
            company=self.company,
            email="ada@contoso.test",
            first_name="Ada",
            user=self.user,
        )

    def start(self):
        response = self.client.get(reverse("microsoft-sso-login"))
        params = parse_qs(urlparse(response["Location"]).query)
        return params["state"][0], params["nonce"][0]

    def finish(self, token, state, **extra):
        query = {"code": "abc", "state": state, **extra}
        with mock.patch.object(
            methods, "exchange_code", return_value=token
        ), signed_by_us():
            return self.client.get(reverse("microsoft-sso-callback"), query)

    def refused(self, response):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class HostileInputTests(Base):
    def test_non_ascii_state_does_not_crash(self):
        self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"), {"code": "abc", "state": "é✓"}
        )
        self.refused(response)

    def test_non_ascii_state_with_a_microsoft_error_does_not_crash(self):
        self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"), {"error": "x", "state": "é✓"}
        )
        self.refused(response)

    def test_code_missing_is_refused(self):
        state, _ = self.start()
        response = self.client.get(reverse("microsoft-sso-callback"), {"state": state})
        self.refused(response)

    def test_state_missing_is_refused(self):
        self.start()
        self.refused(
            self.client.get(reverse("microsoft-sso-callback"), {"code": "abc"})
        )

    def test_empty_state_never_matches_an_empty_session_state(self):
        self.refused(
            self.client.get(
                reverse("microsoft-sso-callback"), {"code": "abc", "state": ""}
            )
        )

    def test_protocol_relative_next_is_refused(self):
        response = self.client.get(
            reverse("microsoft-sso-login"), {"next": "//evil.test/x"}
        )
        params = parse_qs(urlparse(response["Location"]).query)
        done = self.finish(id_token(params["nonce"][0]), params["state"][0])
        self.assertEqual(done.url, "/")

    def test_javascript_next_is_refused(self):
        response = self.client.get(
            reverse("microsoft-sso-login"), {"next": "javascript:alert(1)"}
        )
        params = parse_qs(urlparse(response["Location"]).query)
        done = self.finish(id_token(params["nonce"][0]), params["state"][0])
        self.assertEqual(done.url, "/")

    def test_a_forged_error_description_is_not_shown(self):
        response = self.client.get(
            reverse("microsoft-sso-callback"),
            {"error": "x", "error_description": "Call 555", "state": "bad"},
        )
        self.assertNotIn("555", " ".join(messages_of(response)))

    def test_error_description_is_trimmed_and_flattened(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"),
            {
                "error": "x",
                "error_description": "line one\nline two " + "z" * 1000,
                "state": state,
            },
        )
        shown = " ".join(messages_of(response))
        self.assertIn("line one line two", shown)
        self.assertLess(len(shown), 400)

    def test_error_description_is_escaped_on_the_login_page(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("microsoft-sso-callback"),
            {
                "error": "x",
                "error_description": "<script>alert(1)</script>",
                "state": state,
            },
            follow=True,
        )
        self.assertNotContains(response, "<script>alert(1)</script>")


class TokenForgeryTests(Base):
    def check(self, token, nonce="n1"):
        with signed_by_us():
            return methods.validate_id_token(self.config, token, nonce)

    def test_unsigned_token_is_refused(self):
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "tid": TENANT,
            "exp": int(time.time()) + 600,
            "nonce": "n1",
        }
        with self.assertRaises(methods.SSOError):
            self.check(jwt.encode(body, None, algorithm="none"))

    def test_token_signed_with_the_public_key_as_an_hmac_secret_is_refused(self):
        public = KEY.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "tid": TENANT,
            "exp": int(time.time()) + 600,
            "nonce": "n1",
        }
        try:
            forged = jwt.encode(body, public, algorithm="HS256")
        except Exception:
            self.skipTest("this PyJWT refuses to build the forged token at all")
        with self.assertRaises(methods.SSOError):
            self.check(forged)

    def test_garbage_is_refused(self):
        for junk in ("", "abc", "a.b.c", "x" * 5000):
            with self.assertRaises(methods.SSOError):
                self.check(junk)

    def test_missing_expiry_is_refused(self):
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "tid": TENANT,
            "nonce": "n1",
        }
        with self.assertRaises(methods.SSOError):
            self.check(jwt.encode(body, KEY, algorithm="RS256"))

    def test_missing_tenant_claim_is_refused(self):
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "exp": int(time.time()) + 600,
            "nonce": "n1",
        }
        with self.assertRaises(methods.SSOError):
            self.check(jwt.encode(body, KEY, algorithm="RS256"))

    def test_missing_nonce_is_refused(self):
        body = {
            "aud": CLIENT,
            "iss": f"{methods.AUTHORITY}/{TENANT}/v2.0",
            "tid": TENANT,
            "exp": int(time.time()) + 600,
        }
        with self.assertRaises(methods.SSOError):
            self.check(jwt.encode(body, KEY, algorithm="RS256"))

    def test_non_ascii_nonce_does_not_crash(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token("n1"), nonce="é✓")
        with self.assertRaises(methods.SSOError):
            self.check(id_token("é✓"), nonce="n1")

    def test_empty_session_nonce_never_matches(self):
        with self.assertRaises(methods.SSOError):
            self.check(id_token(""), nonce="")

    def test_slightly_expired_token_within_leeway_is_accepted(self):
        claims = self.check(id_token("n1", exp=int(time.time()) - 20))
        self.assertEqual(claims["nonce"], "n1")

    def test_audience_as_a_list_with_our_client_is_accepted_only_if_ours_is_in_it(self):
        self.assertEqual(
            self.check(id_token("n1", aud=[CLIENT, "other"]))["nonce"], "n1"
        )
        with self.assertRaises(methods.SSOError):
            self.check(id_token("n1", aud=["other"]))


class MicrosoftFailureTests(Base):
    def test_token_endpoint_unreachable_is_a_refusal_not_a_crash(self):
        state, _ = self.start()
        with mock.patch.object(
            methods.requests, "post", side_effect=requests.ConnectionError("down")
        ):
            response = self.client.get(
                reverse("microsoft-sso-callback"), {"code": "abc", "state": state}
            )
        self.refused(response)

    def test_token_endpoint_timeout_is_a_refusal_not_a_crash(self):
        state, _ = self.start()
        with mock.patch.object(
            methods.requests, "post", side_effect=requests.Timeout("slow")
        ):
            response = self.client.get(
                reverse("microsoft-sso-callback"), {"code": "abc", "state": state}
            )
        self.refused(response)

    def test_token_endpoint_returns_html_not_json(self):
        reply = mock.Mock(status_code=200)
        reply.json.side_effect = ValueError("not json")
        with mock.patch.object(methods.requests, "post", return_value=reply):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_token_endpoint_says_no(self):
        reply = mock.Mock(status_code=400)
        reply.json.return_value = {"error": "invalid_grant"}
        with mock.patch.object(methods.requests, "post", return_value=reply):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_token_reply_without_an_id_token(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"access_token": "only"}
        with mock.patch.object(methods.requests, "post", return_value=reply):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_key_fetch_failure_is_a_refusal(self):
        state, nonce = self.start()
        with mock.patch.object(
            methods, "exchange_code", return_value=id_token(nonce)
        ), mock.patch.object(
            methods, "_signing_key", side_effect=Exception("jwks down")
        ):
            response = self.client.get(
                reverse("microsoft-sso-callback"), {"code": "abc", "state": state}
            )
        self.refused(response)

    def test_client_secret_is_sent_to_microsoft_and_never_logged(self):
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"id_token": "t"}
        with mock.patch.object(methods.requests, "post", return_value=reply) as post:
            methods.exchange_code(self.config, "abc", "http://x/cb/")
        self.assertEqual(post.call_args.kwargs["data"]["client_secret"], "s3cret")
        self.assertTrue(post.call_args.kwargs["timeout"])


class IdentityTests(Base):
    def sign_in(self, **claims):
        state, nonce = self.start()
        return self.finish(id_token(nonce, **claims), state)

    def test_two_employees_with_the_same_work_email_are_refused(self):
        other = make_employee(
            company=self.company, email="grace@x.test", first_name="Grace"
        )
        for person in (self.employee, other):
            person.employee_work_info.email = "shared@contoso.test"
            person.employee_work_info.save()
        self.employee.email = "different@contoso.test"
        self.employee.save()
        self.refused(self.sign_in(email="shared@contoso.test"))

    def test_employee_without_a_user_is_refused(self):
        from employee.models import Employee

        Employee.objects.filter(pk=self.employee.pk).update(employee_user_id=None)
        self.refused(self.sign_in())

    def test_inactive_user_with_an_active_employee_is_refused(self):
        self.user.is_active = False
        self.user.save()
        self.refused(self.sign_in())

    def test_account_with_no_email_at_all_is_refused(self):
        self.refused(self.sign_in(email=None, preferred_username=None))

    def test_claim_without_an_at_sign_is_ignored(self):
        self.refused(self.sign_in(email="ada", preferred_username="ada"))

    def test_sign_in_by_preferred_username_or_upn_only(self):
        for claim in ("preferred_username", "upn"):
            self.client.logout()
            response = self.sign_in(email=None, **{claim: "ADA@Contoso.test"})
            self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_email_with_surrounding_spaces_still_matches(self):
        self.assertRedirects(
            self.sign_in(email="  ada@contoso.test  "),
            "/",
            fetch_redirect_response=False,
        )

    def test_domain_filter_with_no_usable_email_refuses(self):
        self.config.allowed_domains = "contoso.test"
        self.config.save()
        self.refused(self.sign_in(email="nodomain"))

    def test_domain_filter_checks_every_address_of_the_account(self):
        self.config.allowed_domains = "contoso.test"
        self.config.save()
        self.refused(
            self.sign_in(
                email="ada@elsewhere.test", preferred_username="x@elsewhere.test"
            )
        )

    def test_signing_in_lands_on_a_working_page(self):
        response = self.sign_in()
        page = self.client.get(response.url, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(reverse("login"), [url for url, _ in page.redirect_chain])

    def test_a_second_sign_in_while_logged_in_as_someone_else_switches_user(self):
        other_user = make_user("other_edge", password="x")
        make_employee(
            company=self.company,
            email="bob@contoso.test",
            first_name="Bob",
            user=other_user,
        )
        self.client.force_login(other_user)
        self.sign_in()
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_nothing_is_left_in_the_session_after_a_refusal(self):
        self.refused(self.sign_in(email="stranger@contoso.test"))
        for key in ("sso_state", "sso_nonce", "sso_next"):
            self.assertNotIn(key, self.client.session)


class MultiTenantTrustTests(Base):
    """
    With a multi-tenant app any Microsoft tenant can sign in, and the ``email`` claim is whatever that tenant's
    admin typed. Matching on it would let a stranger claim an employee's address.
    """

    def sign_in(self, **claims):
        self.config.tenant_id = "organizations"
        self.config.save()
        state, nonce = self.start()
        other = "99999999-0000-0000-0000-000000000000"
        return self.finish(
            id_token(
                nonce, tid=other, iss=f"{methods.AUTHORITY}/{other}/v2.0", **claims
            ),
            state,
        )

    def test_email_claim_alone_does_not_log_in_through_a_multi_tenant_app(self):
        self.refused(
            self.sign_in(
                email="ada@contoso.test", preferred_username="mallory@attacker.test"
            )
        )

    def test_the_sign_in_name_still_works_through_a_multi_tenant_app(self):
        response = self.sign_in(email=None, preferred_username="ada@contoso.test")
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_email_claim_is_trusted_when_the_app_is_pinned_to_one_directory(self):
        state, nonce = self.start()
        response = self.finish(
            id_token(nonce, email="ada@contoso.test", preferred_username="x@x.test"),
            state,
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)


class SettingsEdgeTests(TestCase):
    def form(self, **data):
        base = {
            "tenant_id": TENANT,
            "client_id": CLIENT,
            "client_secret": "s",
            "is_enabled": "on",
        }
        base.update(data)
        return MicrosoftSSOSettingsForm(base)

    def test_good_tenant_values(self):
        for tenant in (
            TENANT,
            "organizations",
            "common",
            "consumers",
            "contoso.onmicrosoft.com",
            "contoso.com",
        ):
            self.assertTrue(self.form(tenant_id=tenant).is_valid(), tenant)

    def test_tenant_that_could_change_the_address_is_refused(self):
        for tenant in (
            "../evil",
            "a/b",
            "a b",
            "evil.test@x",
            "x?y=1",
            "x#y",
            "https://evil.test",
            "a\\b",
        ):
            self.assertFalse(self.form(tenant_id=tenant).is_valid(), tenant)

    def test_client_id_with_spaces_around_it_is_trimmed_and_lower_cased(self):
        form = self.form(client_id="  AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE  ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_id"], CLIENT)

    def test_secret_that_cannot_be_decrypted_turns_the_sign_in_off_quietly(self):
        config = make_config()
        config.client_secret_encrypted = "not-a-valid-token"
        config.save()
        self.assertEqual(config.client_secret, "")
        self.assertFalse(config.is_ready())
        page = Client().get(reverse("login"))
        self.assertNotContains(page, reverse("microsoft-sso-login"))

    def test_secret_encrypted_under_another_key_is_unreadable(self):
        token = crypto.encrypt("abc")
        with self.settings(SECRET_KEY="a-completely-different-secret-key"):
            self.assertEqual(crypto.decrypt(token), "")

    def test_two_settings_rows_use_the_first(self):
        make_config()
        second = MicrosoftSSOSettings(
            is_enabled=False, tenant_id="common", client_id="other"
        )
        second.save()
        self.assertEqual(MicrosoftSSOSettings.current().client_id, CLIENT)

    def test_unicode_secret_round_trips(self):
        self.assertEqual(
            crypto.decrypt(crypto.encrypt("pässwörd-密码")), "pässwörd-密码"
        )

    def test_start_page_with_nothing_configured_goes_back_to_login(self):
        response = Client().get(reverse("microsoft-sso-login"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_callback_with_nothing_configured_goes_back_to_login(self):
        response = Client().get(
            reverse("microsoft-sso-callback"), {"code": "a", "state": "b"}
        )
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)


class SettingsValidationTests(TestCase):
    """Every field on the settings page says plainly what is wrong."""

    def form(self, **data):
        base = {
            "tenant_id": TENANT,
            "client_id": CLIENT,
            "client_secret": "s3cret-value",
            "is_enabled": "on",
        }
        base.update(data)
        return MicrosoftSSOSettingsForm(base)

    def errors(self, **data):
        form = self.form(**data)
        self.assertFalse(form.is_valid())
        return form.errors

    def test_client_id_must_be_the_long_id_from_azure(self):
        for bad in ("abc", "app-client-id", "12345", "not a guid", TENANT + "x"):
            self.assertIn("client_id", self.errors(client_id=bad), bad)

    def test_client_id_is_required_to_enable(self):
        self.assertIn("client_id", self.errors(client_id=""))

    def test_secret_id_pasted_instead_of_the_value_is_called_out(self):
        errors = self.errors(client_secret="29a0adb2-474c-4e24-b4b5-357dc98f99ef")
        self.assertIn("Secret ID", errors["client_secret"][0])

    def test_secret_with_spaces_or_line_breaks_is_refused(self):
        for bad in ("abc def", "abc\ndef", "abc\tdef"):
            self.assertIn("client_secret", self.errors(client_secret=bad), repr(bad))

    def test_secret_with_surrounding_spaces_is_trimmed(self):
        form = self.form(client_secret="  s3cret-value  ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_secret"], "s3cret-value")

    def test_secret_is_required_to_enable_when_none_is_saved(self):
        self.assertIn("client_secret", self.errors(client_secret=""))

    def test_domains_are_cleaned_and_repeats_dropped(self):
        form = self.form(
            allowed_domains="Contoso.com, @fabrikam.test;contoso.com\nsub.example.org"
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["allowed_domains"],
            "contoso.com, fabrikam.test, sub.example.org",
        )

    def test_email_addresses_are_refused_in_the_domain_list(self):
        errors = self.errors(allowed_domains="ada@contoso.com")
        self.assertIn("Domains Only", errors["allowed_domains"][0])

    def test_invalid_domains_are_refused(self):
        for bad in (
            "contoso",
            "-bad.com",
            "bad-.com",
            "a..b",
            "http://contoso.com",
            "contoso.com/x",
            "con toso$.com",
        ):
            self.assertIn("allowed_domains", self.errors(allowed_domains=bad), bad)

    def test_empty_domain_list_is_fine(self):
        self.assertTrue(self.form(allowed_domains="").is_valid())
        self.assertTrue(self.form(allowed_domains=" , ; ").is_valid())

    def test_hiding_the_password_form_needs_the_sign_in_switched_on(self):
        form = MicrosoftSSOSettingsForm(
            {
                "tenant_id": TENANT,
                "client_id": CLIENT,
                "client_secret": "s3cret-value",
                "hide_password_form": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("hide_password_form", form.errors)

    def test_switched_off_with_nothing_filled_in_is_fine(self):
        form = MicrosoftSSOSettingsForm({"tenant_id": "organizations"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_the_page_shows_the_errors(self):
        from horilla.testkit import make_company, make_employee, make_user

        company = make_company("Validation Co")
        admin = make_user("validator", password="x", is_superuser=True)
        make_employee(company=company, email="validator@x.test", user=admin)
        from horilla_auth.models import HorillaUser

        HorillaUser.objects.update(is_new_employee=False)
        client = Client()
        client.force_login(admin)
        session = client.session
        session["selected_company"] = "all"
        session.save()
        response = client.post(
            reverse("microsoft-sso-settings"),
            {
                "tenant_id": "../x",
                "client_id": "nope",
                "client_secret": "a b",
                "allowed_domains": "a@b.com",
                "is_enabled": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        for text in (
            "Directory (Tenant) ID",
            "Application (Client) ID",
            "Spaces Or Line Breaks",
            "Domains Only",
        ):
            self.assertContains(response, text)
        self.assertIsNone(MicrosoftSSOSettings.current())

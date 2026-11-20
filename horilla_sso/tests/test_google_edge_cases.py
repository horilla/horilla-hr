"""Google sign-in under hostile or broken input: forged tokens, odd claims, bad replies, redirects, settings."""

import base64
import hashlib
import hmac
import json
import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from horilla_sso import methods
from horilla_sso.forms import GoogleSSOSettingsForm
from horilla_sso.models import GoogleSSOSettings
from horilla_sso.tests.test_google_sso import (
    CLIENT,
    KEY,
    id_token,
    make_config,
    signed_by_us,
)


def raw_token(claims, key=KEY, algorithm="RS256", headers=None):
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)


def good_claims(nonce="n1", **overrides):
    body = {
        "aud": CLIENT,
        "iss": "https://accounts.google.com",
        "exp": int(time.time()) + 600,
        "nonce": nonce,
        "email": "ada@contoso.test",
        "email_verified": True,
        "hd": "contoso.test",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


class ForgedTokenTests(TestCase):
    def setUp(self):
        self.config = make_config()

    def refused(self, token, nonce="n1"):
        with signed_by_us(), self.assertRaises(methods.SSOError):
            methods.validate_id_token(self.config, token, nonce)

    def test_token_signed_with_a_shared_secret_instead_of_rsa_refused(self):
        """The classic key-confusion attack: HS256 signed with Google's public key as the secret."""
        public_pem = KEY.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )

        def b64(data):
            return base64.urlsafe_b64encode(data).rstrip(b"=")

        head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = b64(json.dumps(good_claims()).encode())
        sig = b64(hmac.new(public_pem, head + b"." + body, hashlib.sha256).digest())
        self.refused((head + b"." + body + b"." + sig).decode())

    def test_token_without_expiry_refused(self):
        claims = good_claims()
        del claims["exp"]
        self.refused(raw_token(claims))

    def test_token_not_yet_valid_refused(self):
        self.refused(raw_token(good_claims(nbf=int(time.time()) + 3600)))

    def test_token_without_audience_refused(self):
        claims = good_claims()
        del claims["aud"]
        self.refused(raw_token(claims))

    def test_token_without_issuer_refused(self):
        claims = good_claims()
        del claims["iss"]
        self.refused(raw_token(claims))

    def test_issuer_with_a_lookalike_host_refused(self):
        for issuer in (
            "https://accounts.google.com.evil.test",
            "http://accounts.google.com",
            "https://accounts.google.com/",
        ):
            self.refused(raw_token(good_claims(iss=issuer)))

    def test_audience_list_without_our_client_refused(self):
        self.refused(
            raw_token(
                good_claims(
                    aud=[
                        "999-a.apps.googleusercontent.com",
                        "888-b.apps.googleusercontent.com",
                    ]
                )
            )
        )

    def test_not_a_token_refused(self):
        for junk in ("", "abc", "a.b.c", "....", "e30.e30.e30"):
            self.refused(junk)

    def test_nonce_of_another_type_refused(self):
        self.refused(raw_token(good_claims(nonce=12345)))
        self.refused(raw_token(good_claims(nonce=["n1"])))

    def test_unknown_signing_key_refused(self):
        with mock.patch.object(
            methods, "_signing_key", side_effect=jwt.PyJWKClientError("no such key")
        ):
            with self.assertRaises(methods.SSOError):
                methods.validate_id_token(self.config, raw_token(good_claims()), "n1")

    def test_google_keys_unreachable_refused(self):
        with mock.patch.object(
            methods, "_signing_key", side_effect=jwt.PyJWKClientConnectionError("down")
        ):
            with self.assertRaises(methods.SSOError):
                methods.validate_id_token(self.config, raw_token(good_claims()), "n1")

    def test_email_verified_must_be_a_real_yes(self):
        for value in (False, "false", "False", 0, 1, "yes", None, [], {}, "True"):
            self.refused(raw_token(good_claims(email_verified=value)))

    def test_email_verified_text_true_is_accepted(self):
        with signed_by_us():
            claims = methods.validate_id_token(
                self.config, raw_token(good_claims(email_verified="true")), "n1"
            )
        self.assertEqual(claims["email"], "ada@contoso.test")


class OddClaimTests(TestCase):
    def setUp(self):
        self.config = make_config()
        self.company = make_company("Claims Co")
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

    def test_hosted_domain_that_only_ends_the_same_refused(self):
        self.assertFalse(
            self.allowed(hd="evilcontoso.test", email="ada@evilcontoso.test")
        )
        self.assertFalse(
            self.allowed(
                hd="contoso.test.evil.test", email="ada@contoso.test.evil.test"
            )
        )

    def test_email_domain_that_extends_the_hosted_domain_refused(self):
        self.assertFalse(self.allowed(email="ada@contoso.test.evil.test"))

    def test_email_with_two_at_signs_does_not_slip_through_the_domain_check(self):
        self.assertFalse(
            self.allowed(email="ada@evil.test@contoso.test")
            and methods.find_employee(
                {"email": "ada@evil.test@contoso.test", "email_verified": True},
                provider="google",
            )
        )

    def test_claims_of_the_wrong_type_never_pass(self):
        for hd in (["contoso.test"], {"a": 1}, 7, True, ""):
            self.assertFalse(self.allowed(hd=hd))
        for email in (["ada@contoso.test"], {"e": "ada@contoso.test"}, 7, True, ""):
            self.assertFalse(
                self.allowed(email=email)
                and methods.find_employee(
                    {"email": email, "email_verified": True}, provider="google"
                )
            )

    def test_email_with_spaces_and_capitals_still_matches(self):
        claims = {"email": "  ADA@Contoso.TEST ", "email_verified": True}
        self.assertEqual(
            methods.find_employee(claims, provider="google"), self.employee
        )

    def test_email_without_an_at_sign_matches_nobody(self):
        self.assertIsNone(
            methods.find_employee(
                {"email": "ada", "email_verified": True}, provider="google"
            )
        )

    def test_sql_like_email_matches_nobody(self):
        for email in (
            "' OR 1=1 --@contoso.test",
            "%@contoso.test",
            "ada@contoso.test' --",
        ):
            self.assertIsNone(
                methods.find_employee(
                    {"email": email, "email_verified": True}, provider="google"
                )
            )

    def test_domains_saved_in_capitals_are_still_compared_lower_case(self):
        self.config.allowed_domains = "Contoso.Test"
        self.assertTrue(self.allowed())

    def test_hosted_domain_and_email_in_different_case_pass(self):
        self.assertTrue(self.allowed(hd="CONTOSO.test", email="ADA@contoso.TEST"))

    def test_google_never_reads_microsoft_style_claims(self):
        self.assertIsNone(
            methods.find_employee(
                {"email_verified": True, "preferred_username": "ada@contoso.test"},
                provider="google",
            )
        )


class HostileCallbackTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.config = make_config()
        self.company = make_company("Hostile Co")
        self.user = make_user("ada", password="x")
        self.employee = make_employee(
            company=self.company,
            email="ada@contoso.test",
            first_name="Ada",
            user=self.user,
        )

    def start(self, **query):
        response = self.client.get(reverse("google-sso-login"), query)
        params = parse_qs(urlparse(response["Location"]).query)
        return params["state"][0], params["nonce"][0]

    def finish(self, token, state, **extra):
        with mock.patch.object(
            methods, "exchange_code", return_value=token
        ), signed_by_us():
            return self.client.get(
                reverse("google-sso-callback"), {"code": "abc", "state": state, **extra}
            )

    def refused(self, response):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_redirect_tricks_land_on_the_home_page(self):
        for target in (
            "//evil.test",
            "https://evil.test/x",
            "javascript:alert(1)",
            "/\\evil.test",
            "http:evil.test",
            "///evil.test",
        ):
            self.client.logout()
            state, nonce = self.start(next=target)
            self.assertEqual(self.finish(id_token(nonce), state).url, "/", target)

    def test_a_local_next_with_a_query_is_kept(self):
        state, nonce = self.start(next="/employee/?view=list")
        self.assertEqual(
            self.finish(id_token(nonce), state).url, "/employee/?view=list"
        )

    def test_huge_state_is_refused_without_a_server_error(self):
        _, nonce = self.start()
        self.refused(self.finish(id_token(nonce), "x" * 20000))

    def test_state_with_control_characters_is_refused(self):
        _, nonce = self.start()
        self.refused(self.finish(id_token(nonce), "ab\x00cd\n"))

    def test_code_and_state_given_twice_use_the_last_value_safely(self):
        state, nonce = self.start()
        with mock.patch.object(
            methods, "exchange_code", return_value=id_token(nonce)
        ), signed_by_us():
            response = self.client.get(
                reverse("google-sso-callback")
                + f"?code=a&code=b&state=forged&state={state}"
            )
        self.assertEqual(response.status_code, 302)

    def test_post_to_the_callback_is_refused_cleanly(self):
        self.refused(
            self.client.post(
                reverse("google-sso-callback"), {"code": "a", "state": "b"}
            )
        )

    def test_post_to_the_start_still_redirects_to_google_only(self):
        response = self.client.post(reverse("google-sso-login"))
        self.assertTrue(response["Location"].startswith("https://accounts.google.com/"))

    def test_error_text_from_the_url_is_escaped_on_the_login_page(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("google-sso-callback"),
            {
                "error": "access_denied",
                "error_description": "<script>alert(1)</script>",
                "state": state,
            },
            follow=True,
        )
        body = response.content.decode()
        self.assertNotIn("<script>alert(1)</script>", body)

    def test_a_very_long_error_text_is_cut(self):
        state, _ = self.start()
        response = self.client.get(
            reverse("google-sso-callback"),
            {"error": "x", "error_description": "A" * 5000, "state": state},
        )
        self.assertLess(
            len(str([str(m) for m in get_messages(response.wsgi_request)][0])), 400
        )

    def test_error_and_code_together_is_still_an_error(self):
        state, nonce = self.start()
        with mock.patch.object(
            methods, "exchange_code", return_value=id_token(nonce)
        ) as exchange, signed_by_us():
            response = self.client.get(
                reverse("google-sso-callback"),
                {"error": "access_denied", "code": "abc", "state": state},
            )
        exchange.assert_not_called()
        self.refused(response)

    def test_signing_in_is_refused_when_google_is_switched_off_midway(self):
        state, nonce = self.start()
        self.config.is_enabled = False
        self.config.save()
        self.refused(self.finish(id_token(nonce), state))

    def test_signing_in_is_refused_when_the_domain_is_removed_midway(self):
        state, nonce = self.start()
        self.config.allowed_domains = ""
        self.config.save()
        self.refused(self.finish(id_token(nonce), state))

    def test_an_unreadable_saved_secret_turns_the_sign_in_off(self):
        GoogleSSOSettings.objects.update(client_secret_encrypted="not-a-valid-token")
        self.assertNotContains(
            Client().get(reverse("login")), reverse("google-sso-login")
        )
        self.assertRedirects(
            self.client.get(reverse("google-sso-login")),
            reverse("login"),
            fetch_redirect_response=False,
        )

    def test_user_archived_but_employee_active_refused(self):
        self.user.is_active = False
        self.user.save()
        state, nonce = self.start()
        self.refused(self.finish(id_token(nonce), state))

    def test_employee_without_a_user_refused(self):
        from employee.models import Employee

        Employee.objects.filter(pk=self.employee.pk).update(employee_user_id=None)
        state, nonce = self.start()
        self.refused(self.finish(id_token(nonce), state))

    def test_garbage_in_place_of_the_token_is_refused_without_a_server_error(self):
        for junk in ("not-a-token", 12345, ["a", "b"], {"x": 1}):
            self.client.logout()
            state, _ = self.start()
            self.refused(self.finish(junk, state))

    def test_starting_microsoft_in_between_cancels_the_google_sign_in(self):
        from horilla_sso.tests.test_microsoft_sso import (
            make_config as make_microsoft_config,
        )

        make_microsoft_config()
        state, nonce = self.start()
        self.client.get(reverse("microsoft-sso-login"))
        self.refused(self.finish(id_token(nonce), state))

    def test_a_second_sign_in_replaces_the_first(self):
        first, nonce1 = self.start()
        second, nonce2 = self.start()
        self.refused(self.finish(id_token(nonce1), first))
        self.client.logout()
        state, nonce = self.start()
        self.assertEqual(self.finish(id_token(nonce), state).status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_a_logged_in_user_signing_in_again_stays_themselves(self):
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        before = self.client.session["_auth_user_id"]
        state, nonce = self.start()
        self.finish(id_token(nonce), state)
        self.assertEqual(self.client.session["_auth_user_id"], before)


class BrokenGoogleReplyTests(TestCase):
    def setUp(self):
        self.config = make_config()

    def reply(self, status, body):
        response = mock.Mock(status_code=status)
        if isinstance(body, Exception):
            response.json.side_effect = body
        else:
            response.json.return_value = body
        return response

    def refused(self, status, body):
        with mock.patch.object(
            methods.requests, "post", return_value=self.reply(status, body)
        ):
            with self.assertRaises(methods.SSOError):
                methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_reply_that_is_a_list_refused(self):
        self.refused(200, ["id_token"])

    def test_reply_that_is_text_refused(self):
        self.refused(200, "id_token")

    def test_reply_that_is_empty_refused(self):
        self.refused(200, None)

    def test_reply_without_a_token_refused(self):
        self.refused(200, {"access_token": "x"})

    def test_reply_with_an_empty_token_refused(self):
        self.refused(200, {"id_token": ""})

    def test_error_status_with_a_token_refused(self):
        self.refused(400, {"id_token": "x"})

    def test_server_error_refused(self):
        self.refused(500, ValueError("html"))

    def test_slow_google_refused(self):
        for error in (
            requests.Timeout("slow"),
            requests.ConnectionError("down"),
            requests.exceptions.SSLError("tls"),
        ):
            with mock.patch.object(methods.requests, "post", side_effect=error):
                with self.assertRaises(methods.SSOError):
                    methods.exchange_code(self.config, "abc", "http://x/cb/")

    def test_the_request_has_a_timeout_and_never_sends_the_code_in_the_url(self):
        with mock.patch.object(
            methods.requests, "post", return_value=self.reply(200, {"id_token": "t"})
        ) as post:
            methods.exchange_code(self.config, "the-code", "http://x/cb/")
        self.assertIn("timeout", post.call_args.kwargs)
        self.assertNotIn("the-code", post.call_args.args[0])


class SettingsEdgeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = make_company("Edge Settings Co")
        self.admin = make_user("root", password="x", is_superuser=True)
        make_employee(company=self.company, email="root@x.test", user=self.admin)

    def form(self, **data):
        base = {
            "client_id": CLIENT,
            "client_secret": "GOCSPX-abc",
            "allowed_domains": "contoso.test",
            "is_enabled": "on",
        }
        base.update(data)
        return GoogleSSOSettingsForm(base)

    def test_logged_out_visitor_is_sent_away(self):
        response = self.client.get(reverse("google-sso-settings"))
        self.assertNotEqual(response.status_code, 200)

    def test_a_plain_user_cannot_change_the_settings(self):
        user = make_user("plain", password="x")
        make_employee(company=self.company, email="plain@x.test", user=user)
        self.client.force_login(user)
        self.client.post(
            reverse("google-sso-settings"),
            {
                "client_id": CLIENT,
                "client_secret": "GOCSPX-abc",
                "allowed_domains": "evil.test",
                "is_enabled": "on",
            },
        )
        self.assertIsNone(GoogleSSOSettings.current())

    def test_a_valid_form_is_valid(self):
        self.assertTrue(self.form().is_valid())

    def test_client_id_shapes(self):
        for bad in (
            "1234.apps.googleusercontent.com",
            "abc-def.apps.googleusercontent.com",
            "123-abc.apps.googleusercontent.com.evil.test",
            "https://123-abc.apps.googleusercontent.com",
            "123-abc.apps.googleusercontent.com extra",
            "123-abc.apps.googleusercontent.comx",
            "x" * 300,
        ):
            self.assertIn("client_id", self.form(client_id=bad).errors, bad)

    def test_client_id_in_capitals_is_lower_cased(self):
        form = self.form(client_id="123-ABC.APPS.GOOGLEUSERCONTENT.COM")
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["client_id"], "123-abc.apps.googleusercontent.com"
        )

    def test_client_id_with_surrounding_spaces_is_trimmed(self):
        form = self.form(client_id="  123-abc.apps.googleusercontent.com  ")
        self.assertTrue(form.is_valid())

    def test_secret_that_is_a_line_break_pasted_in_refused(self):
        self.assertIn(
            "client_secret", self.form(client_secret="GOCSPX-abc\ndef").errors
        )
        self.assertIn("client_secret", self.form(client_secret="GOCSPX abc").errors)

    def test_very_long_secret_does_not_break_saving(self):
        form = self.form(client_secret="GOCSPX-" + "a" * 5000)
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(len(GoogleSSOSettings.current().client_secret), 5007)

    def test_domain_entries(self):
        for bad in (
            "contoso",
            "ada@contoso.test",
            "-contoso.test",
            "contoso..test",
            "contoso.test/path",
            "https://contoso.test",
            "con toso.test!",
            "bücher.de",
            "contoso.test.",
            "*.contoso.test",
        ):
            self.assertIn("allowed_domains", self.form(allowed_domains=bad).errors, bad)

    def test_many_domains_over_the_limit_refused(self):
        many = ", ".join(f"d{i:03d}.example.test" for i in range(40))
        self.assertIn("allowed_domains", self.form(allowed_domains=many).errors)

    def test_domains_separated_by_odd_characters_are_accepted(self):
        form = self.form(allowed_domains="a.test;b.test c.test,\nd.test")
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["allowed_domains"], "a.test, b.test, c.test, d.test"
        )

    def test_a_failed_save_does_not_wipe_the_saved_secret(self):
        saved = self.form()
        self.assertTrue(saved.is_valid())
        saved.save()
        self.client.force_login(self.admin)
        self.client.post(
            reverse("google-sso-settings"),
            {
                "client_id": "bad",
                "client_secret": "",
                "allowed_domains": "contoso.test",
                "is_enabled": "on",
            },
        )
        self.assertEqual(GoogleSSOSettings.current().client_secret, "GOCSPX-abc")
        self.assertEqual(GoogleSSOSettings.current().client_id, CLIENT)

    def test_switching_off_keeps_the_secret_and_the_domains(self):
        self.form().save()
        self.client.force_login(self.admin)
        self.client.post(
            reverse("google-sso-settings"),
            {
                "client_id": CLIENT,
                "client_secret": "GOCSPX-abc",
                "allowed_domains": "contoso.test",
            },
        )
        config = GoogleSSOSettings.current()
        self.assertFalse(config.is_enabled)
        self.assertEqual(
            (config.client_secret, config.allowed_domains),
            ("GOCSPX-abc", "contoso.test"),
        )

    def test_saving_twice_keeps_a_single_row(self):
        self.client.force_login(self.admin)
        payload = {
            "client_id": CLIENT,
            "client_secret": "GOCSPX-abc",
            "allowed_domains": "contoso.test",
            "is_enabled": "on",
        }
        self.client.post(reverse("google-sso-settings"), payload)
        self.client.post(reverse("google-sso-settings"), payload)
        self.assertEqual(GoogleSSOSettings.objects.count(), 1)

    def test_extra_unknown_fields_in_the_post_are_ignored(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("google-sso-settings"),
            {
                "client_id": CLIENT,
                "client_secret": "GOCSPX-abc",
                "allowed_domains": "contoso.test",
                "is_enabled": "on",
                "client_secret_encrypted": "forged",
                "id": "99",
            },
        )
        self.assertEqual(GoogleSSOSettings.current().client_secret, "GOCSPX-abc")

    def test_the_secret_is_not_in_the_page_source_of_the_login_page(self):
        make_config()
        self.assertNotContains(Client().get(reverse("login")), "GOCSPX")

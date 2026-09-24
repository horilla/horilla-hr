"""
Functional tests for the SSO request flow: state handling, employee
matching, the cross-tenant check, and the settings-view permission gate.

oidc_client.exchange_code_for_tokens / verify_id_token are mocked here --
their own correctness (signature/audience/nonce/expiry validation) is
covered in test_oidc_client.py against a real RSA keypair. These tests
are about what sso_callback does with a claims dict once it has one:
does it find the right employee, refuse the wrong one, and never create
an account.
"""

from unittest import mock

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

from horilla_oidc.models import OidcProvider

CLAIMS = {"email": "person@test.horilla", "email_verified": True}


def make_provider(company, **overrides):
    defaults = {
        "display_name": "Test IdP",
        "issuer": "https://idp.test",
        "client_id": "client-1",
    }
    defaults.update(overrides)
    provider = OidcProvider(company=company, **defaults)
    provider.client_secret = "secret-value"
    provider.save()
    return provider


class SsoLoginTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.provider = make_provider(self.company)
        self.client = Client()

    def test_redirects_to_the_authorization_endpoint(self):
        with mock.patch(
            "horilla_oidc.oidc_client.get_discovery",
            return_value={"authorization_endpoint": "https://idp.test/auth"},
        ):
            response = self.client.get(reverse("oidc_login", args=[self.provider.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://idp.test/auth?"))
        self.assertIn("oidc_state", self.client.session)
        self.assertIn("oidc_nonce", self.client.session)
        self.assertEqual(self.client.session["oidc_provider_slug"], self.provider.slug)

    def test_disabled_provider_404s(self):
        self.provider.is_enabled = False
        self.provider.save()
        response = self.client.get(reverse("oidc_login", args=[self.provider.slug]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_slug_404s(self):
        response = self.client.get(reverse("oidc_login", args=["no-such-company"]))
        self.assertEqual(response.status_code, 404)


class SsoCallbackTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.other_company = make_company("Globex")
        self.provider = make_provider(self.company)
        self.client = Client()

    def _start_flow(self):
        """Puts the session into the state sso_login would have left it in."""
        session = self.client.session
        session["oidc_state"] = "the-state"
        session["oidc_nonce"] = "the-nonce"
        session["oidc_provider_slug"] = self.provider.slug
        session["oidc_state_ts"] = __import__("time").time()
        session.save()

    def _callback(self, state="the-state", **claims_overrides):
        self._start_flow()
        claims = {**CLAIMS, **claims_overrides}
        with mock.patch(
            "horilla_oidc.oidc_client.get_discovery", return_value={}
        ), mock.patch(
            "horilla_oidc.oidc_client.exchange_code_for_tokens",
            return_value={"id_token": "opaque-token"},
        ), mock.patch(
            "horilla_oidc.oidc_client.verify_id_token", return_value=claims
        ):
            return self.client.get(
                reverse("oidc_callback", args=[self.provider.slug]),
                {"code": "auth-code", "state": state},
            )

    def test_happy_path_signs_the_matching_employee_in(self):
        employee = make_employee(company=self.company, email=CLAIMS["email"])
        response = self._callback()
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), employee.employee_user_id_id
        )

    def test_no_matching_employee_is_refused_and_creates_nothing(self):
        from employee.models import Employee

        before = Employee.objects.count()
        response = self._callback()
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(Employee.objects.count(), before)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_employee_in_a_different_company_is_refused(self):
        """
        The cross-tenant check: Employee.email is globally unique, not
        per-company, so a matching email alone must not be enough --
        Globex's employee must not be able to sign in through Acme's IdP.
        """
        make_employee(company=self.other_company, email=CLAIMS["email"])
        response = self._callback()
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_employee_is_refused(self):
        employee = make_employee(company=self.company, email=CLAIMS["email"])
        employee.is_active = False
        employee.save()
        response = self._callback()
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_state_is_refused(self):
        make_employee(company=self.company, email=CLAIMS["email"])
        response = self._callback(state="an-attacker-supplied-state")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_state_minted_for_a_different_company_is_refused(self):
        """A state token from one company's flow replayed at another's callback."""
        other_provider = make_provider(self.other_company, client_id="client-2")
        make_employee(company=self.other_company, email=CLAIMS["email"])

        session = self.client.session
        session["oidc_state"] = "the-state"
        session["oidc_nonce"] = "the-nonce"
        session["oidc_provider_slug"] = self.provider.slug  # minted for Acme
        session["oidc_state_ts"] = __import__("time").time()
        session.save()

        with mock.patch(
            "horilla_oidc.oidc_client.get_discovery", return_value={}
        ), mock.patch(
            "horilla_oidc.oidc_client.exchange_code_for_tokens",
            return_value={"id_token": "opaque-token"},
        ), mock.patch(
            "horilla_oidc.oidc_client.verify_id_token", return_value=CLAIMS
        ):
            response = self.client.get(
                reverse("oidc_callback", args=[other_provider.slug]),  # presented at Globex's
                {"code": "auth-code", "state": "the-state"},
            )
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_idp_error_is_refused(self):
        self._start_flow()
        response = self.client.get(
            reverse("oidc_callback", args=[self.provider.slug]),
            {"error": "access_denied"},
        )
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_superuser_is_refused(self):
        """
        Found live: a non-superuser holding the settings permission pointed
        Acme at their own IdP and signed in as the superuser. A superuser is
        global, so no single company's IdP may vouch for one.
        """
        admin = make_user("root", is_superuser=True)
        make_employee(company=self.company, email=CLAIMS["email"], user=admin)
        response = self._callback()
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_exact_case_email_wins_over_case_insensitive_match(self):
        make_employee(company=self.company, email="Person@test.horilla", first_name="Aaa")
        exact = make_employee(company=self.company, email=CLAIMS["email"], first_name="Zzz")
        self._callback()
        self.assertEqual(int(self.client.session["_auth_user_id"]), exact.employee_user_id_id)

    def test_ambiguous_case_insensitive_match_is_refused(self):
        make_employee(company=self.company, email="Person@test.horilla")
        make_employee(company=self.company, email="PERSON@test.horilla")
        self._callback()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_junk_callbacks_do_not_lock_out_real_logins(self):
        """Found live: 20 anonymous junk callbacks used to block the company's SSO."""
        employee = make_employee(company=self.company, email=CLAIMS["email"])
        for _ in range(25):
            self.client.get(
                reverse("oidc_callback", args=[self.provider.slug]), {"code": "x", "state": "y"}
            )
        self._callback()
        self.assertEqual(int(self.client.session["_auth_user_id"]), employee.employee_user_id_id)

    def test_safe_next_is_honoured_and_offsite_next_is_not(self):
        make_employee(company=self.company, email=CLAIMS["email"])
        for next_url, expected in [("/leave/user-leave/", "/leave/user-leave/"), ("https://evil.test/", "/")]:
            session = self.client.session
            session["oidc_next"] = next_url
            session.save()
            response = self._callback()
            self.assertEqual(response.url, expected)
            self.client.logout()

    def test_successful_login_sets_2fa_skip_when_enabled(self):
        make_employee(company=self.company, email=CLAIMS["email"])
        self.provider.skip_2fa_for_sso = True
        self.provider.save()
        self._callback()
        self.assertTrue(self.client.session.get("otp_code_verified"))

    def test_successful_login_does_not_skip_2fa_when_disabled(self):
        make_employee(company=self.company, email=CLAIMS["email"])
        self.provider.skip_2fa_for_sso = False
        self.provider.save()
        self._callback()
        self.assertNotIn("otp_code_verified", self.client.session)


class OidcSettingsViewTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        self.admin_user = make_user("admin_user")
        make_employee(company=self.company, email="admin@test.horilla", user=self.admin_user)
        self.client = Client()

    def _login_with_selected_company(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["selected_company"] = self.company.pk
        session.save()

    def test_the_model_permission_alone_does_not_show_the_form(self):
        """
        Whoever controls the issuer can sign in as anyone in the company, so
        this is superuser-only; a delegable model permission is not enough.
        """
        self.admin_user.user_permissions.add(Permission.objects.get(codename="change_oidcprovider"))
        self._login_with_selected_company(self.admin_user)
        response = self.client.get(reverse("oidc-settings"))
        self.assertNotContains(response, "client_secret", status_code=response.status_code)

    def test_superuser_sees_the_form_and_the_redirect_uri(self):
        self.admin_user.is_superuser = True
        self.admin_user.save()
        make_provider(self.company)
        self._login_with_selected_company(self.admin_user)
        response = self.client.get(reverse("oidc-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "client_secret")
        self.assertContains(response, "/accounts/sso/acme/callback/")

    def test_saving_clears_the_cached_discovery_document(self):
        """Found live: a changed issuer kept redirecting to the old IdP for 24h."""
        from django.core.cache import cache

        from horilla_oidc.oidc_client import discovery_cache_key

        provider = make_provider(self.company)
        cache.set(discovery_cache_key(provider), {"authorization_endpoint": "https://old.test/auth"})
        provider.issuer = "https://new.test"
        provider.save()
        self.assertIsNone(cache.get(discovery_cache_key(provider)))

    def test_saving_creates_a_provider_for_the_selected_company(self):
        self.admin_user.is_superuser = True
        self.admin_user.save()
        self._login_with_selected_company(self.admin_user)

        response = self.client.post(
            reverse("oidc-settings"),
            {
                "display_name": "Sign in with Okta",
                "issuer": "https://acme.okta.com",
                "client_id": "abc123",
                "is_enabled": "on",
                "client_secret": "top-secret",
                "scopes": "openid email profile",
                "authorization_endpoint": "",
                "token_endpoint": "",
                "jwks_uri": "",
            },
        )
        self.assertRedirects(response, reverse("oidc-settings"))
        provider = OidcProvider.objects.get(company=self.company)
        self.assertEqual(provider.client_secret, "top-secret")

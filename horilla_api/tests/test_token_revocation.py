"""Token invalidation on the API.

Access tokens here last 60 minutes and there is no refresh endpoint, so the
only thing standing between a leaked or stale token and the API is what
authentication checks on each request.

Two conditions matter, and SimpleJWT implements both -- one on by default,
one that has to be turned on:

  * CHECK_USER_IS_ACTIVE rejects a token whose user has been deactivated.
    This is already the default; the test pins it so a future settings edit
    cannot switch it off unnoticed.
  * CHECK_REVOKE_TOKEN embeds a hash of the password in the token and
    rejects it once the stored hash changes, which makes a password change
    revoke every token issued before it.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

LOGIN_URL = "/api/v1/auth/login/"
# Any authenticated endpoint will do; this one only needs a valid token.
PROBE_URL = "/api/v1/employee/list/employees/"


class TokenRevocationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Revocation Co")
        self.user = make_user("revoke_user", password="secret123")
        self.employee = make_employee(
            company=self.company,
            email="revoke@test.horilla",
            user=self.user,
        )

    def _token(self):
        response = self.client.post(
            LOGIN_URL,
            {"username": "revoke_user", "password": "secret123"},
            format="json",
        )
        self.assertEqual(
            response.status_code, 200, f"login failed: {response.content!r}"
        )
        return response.data["access"]

    def _get(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client.get(PROBE_URL)

    def test_token_works_before_anything_changes(self):
        """A control: without it, the two tests below pass on a token that
        never worked in the first place."""
        self.assertEqual(self._get(self._token()).status_code, 200)

    def test_deactivating_the_user_invalidates_the_token(self):
        token = self._token()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.assertNotEqual(
            self._get(token).status_code,
            200,
            "a deactivated user's token was still accepted",
        )

    def test_changing_the_password_invalidates_the_token(self):
        """Requires CHECK_REVOKE_TOKEN. Without it the old token stays valid
        for its full 60 minutes after a password reset."""
        token = self._token()
        self.user.set_password("a-different-password")
        self.user.save(update_fields=["password"])

        self.assertNotEqual(
            self._get(token).status_code,
            200,
            "a token issued before the password change was still accepted",
        )

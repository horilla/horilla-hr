"""Company scoping and field exposure on the LinkedIn account endpoint.

LinkedInAccount rows hold an `api_token`, so this endpoint is the one place
in the recruitment API where a scoping gap leaks a credential rather than
ordinary HR data.

Company scoping itself holds: TenantScopedJWTAuthentication sets the tenant
ContextVar before any queryset is built, so a cross-company read by pk is
already refused. The cross-company case is kept as a fence -- it is the
assertion that would fail if that authentication class were ever dropped
from DEFAULT_AUTHENTICATION_CLASSES.

Note the shape these deliberately avoid: authenticating with
force_authenticate() bypasses the authentication class, so the ContextVar
stays unset, HorillaCompanyManager adds no predicate, and the test "proves"
a leak on a path no real caller takes. These log in for a real token.

Two defects that did survive that check:

  * the serializer declared `fields = "__all__"`, so api_token -- a
    credential -- was emitted in every response body;
  * the list route raised FieldError, because permission_based_queryset
    narrows on employee_id and LinkedInAccount has no such field.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from recruitment.models import LinkedInAccount

DETAIL_URL = "/api/v1/recruitment/linkedin-account/{pk}/"
LIST_URL = "/api/v1/recruitment/linkedin-account/"

SECRET = "tok-company-b-must-not-leak"


class LinkedInAccountScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)

        self.company_a = make_company("LinkedIn Tenant A")
        self.company_b = make_company("LinkedIn Tenant B", hq=False)

        self.user_a = make_user("li_tenant_a", password="secret123")
        self.employee_a = make_employee(
            company=self.company_a,
            email="li_a@test.horilla",
            first_name="Alice",
            user=self.user_a,
        )

        # Company B's row: the credential that must stay in company B.
        self.account_b = LinkedInAccount.objects.create(
            username="B App",
            email="b@example.com",
            api_token=SECRET,
            sub_id="sub-b",
            company_id=self.company_b,
        )

    def _login(self):
        """Authenticate with a real token, not force_authenticate.

        force_authenticate sets request.user directly and skips the
        authentication class -- but TenantScopedJWTAuthentication is exactly
        what calls set_selected_company(), so bypassing it leaves the
        ContextVar unset and HorillaCompanyManager unscoped. A test using it
        would prove a path no real caller takes.
        """
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "li_tenant_a", "password": "secret123"},
            format="json",
        )
        self.assertEqual(
            response.status_code, 200, f"login failed: {response.content!r}"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_detail_route_does_not_expose_another_companys_account(self):
        """A company A user must not retrieve company B's row by pk."""
        self._login()

        response = self.client.get(DETAIL_URL.format(pk=self.account_b.pk))

        self.assertNotEqual(
            response.status_code,
            200,
            "company A retrieved company B's LinkedIn account by pk",
        )

    def test_api_token_is_never_serialised(self):
        """Even for a reachable row, the credential must not be returned.

        Defence in depth: this holds regardless of the scoping fix, so a
        future route that legitimately serves this model cannot leak the
        token by accident.
        """
        self._login()
        own = LinkedInAccount.objects.create(
            username="A App",
            email="a@example.com",
            api_token="tok-company-a",
            sub_id="sub-a",
            company_id=self.company_a,
        )

        response = self.client.get(DETAIL_URL.format(pk=own.pk))

        if response.status_code == 200:
            self.assertNotIn(
                "api_token",
                response.json(),
                "the endpoint serialised api_token",
            )

    def test_list_route_does_not_expose_another_companys_token(self):
        """The list path must not carry the token either."""
        self._login()

        response = self.client.get(LIST_URL)

        self.assertNotIn(
            SECRET,
            response.content.decode(),
            "company B's api_token appeared in company A's list response",
        )

"""
Company scoping on the API path.

Tenant scoping rests on a ContextVar that CompanyMiddleware sets, but
middleware runs before DRF resolves the JWT -- so on a tokened request the
ContextVar is unset unless the authentication class sets it, and
HorillaCompanyManager adds no company predicate when it is unset.

These tests pin that behaviour. Note the shape they deliberately avoid:
asserting only that a user can see its own data passes whether or not
scoping is applied, so each assertion below also checks that the *other*
company's rows are absent, and does so symmetrically.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import get_selected_company, set_selected_company
from horilla.testkit import make_company, make_employee, make_user

# Real routes, read off the URL conf. The unversioned paths guessed
# earlier 404d, which made the end-to-end assertions skip -- i.e. the two
# tests that actually prove isolation were silently not running.
LOGIN_URL = "/api/v1/auth/login/"
EMPLOYEE_LIST_URL = "/api/v1/employee/list/employees/"


class ApiTenantScopingTests(TestCase):
    """Two companies, two users; each must see only its own."""

    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)

        self.company_a = make_company("Tenant A")
        self.company_b = make_company("Tenant B", hq=False)

        self.user_a = make_user("tenant_a_user", password="secret123")
        self.employee_a = make_employee(
            company=self.company_a,
            email="tenant_a@test.horilla",
            first_name="Alice",
            user=self.user_a,
        )
        # Grant view_employee to both. Without it EmployeeListAPIView takes
        # its subordinates-only branch, which returns nothing for these users
        # -- so the isolation assertions would pass on an empty list whether
        # or not scoping works. The permission puts them on the branch that
        # actually queries Employee.objects, which is what we need to test.
        from django.contrib.auth.models import Permission

        view_employee = Permission.objects.get(
            codename="view_employee", content_type__app_label="employee"
        )
        self.user_a.user_permissions.add(view_employee)

        self.user_b = make_user("tenant_b_user", password="secret123")
        self.employee_b = make_employee(
            company=self.company_b,
            email="tenant_b@test.horilla",
            first_name="Bob",
            user=self.user_b,
        )
        self.user_b.user_permissions.add(view_employee)

    def tearDown(self):
        set_selected_company(None)

    def _token(self, username):
        response = self.client.post(
            LOGIN_URL,
            {"username": username, "password": "secret123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["access"]

    # -- the resolver -----------------------------------------------------

    def test_resolver_returns_the_users_own_company(self):
        from horilla_api.authentication import resolve_company_id

        self.assertEqual(resolve_company_id(self.user_a), self.company_a.id)
        self.assertEqual(resolve_company_id(self.user_b), self.company_b.id)

    def test_resolver_returns_none_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        from horilla_api.authentication import resolve_company_id

        self.assertIsNone(resolve_company_id(AnonymousUser()))
        self.assertIsNone(resolve_company_id(None))

    def test_resolver_returns_none_for_superuser(self):
        """Superusers stay tenant-wide, matching the web path."""
        from horilla_api.authentication import resolve_company_id

        root = make_user("tenant_root", password="secret123", is_superuser=True)
        self.assertIsNone(resolve_company_id(root))

    # -- the authentication class ----------------------------------------

    def test_authenticating_sets_the_company_contextvar(self):
        """Scope is established when the token is resolved.

        Without it, get_selected_company() is None inside the view and
        HorillaCompanyManager adds no company predicate.
        """
        from rest_framework.test import APIRequestFactory

        from horilla_api.authentication import TenantScopedJWTAuthentication

        token = self._token("tenant_a_user")
        request = APIRequestFactory().get(
            EMPLOYEE_LIST_URL, HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        set_selected_company(None)
        self.assertIsNone(get_selected_company())

        user, _validated = TenantScopedJWTAuthentication().authenticate(request)

        self.assertEqual(user, self.user_a)
        self.assertEqual(get_selected_company(), self.company_a.id)

    def test_no_credentials_leaves_scope_unset(self):
        from rest_framework.test import APIRequestFactory

        from horilla_api.authentication import TenantScopedJWTAuthentication

        request = APIRequestFactory().get(EMPLOYEE_LIST_URL)
        self.assertIsNone(TenantScopedJWTAuthentication().authenticate(request))

    def test_configured_as_the_default_authentication_class(self):
        """A correct class nothing is wired to would fix nothing."""
        from django.conf import settings

        configured = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
        self.assertIn(
            "horilla_api.authentication.TenantScopedJWTAuthentication",
            configured,
        )

    # -- end to end -------------------------------------------------------

    def test_employee_list_excludes_the_other_tenant(self):
        """A company's list must contain only its own employees."""
        token = self._token("tenant_a_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(EMPLOYEE_LIST_URL)

        self.assertEqual(response.status_code, 200, response.data)

        body = str(response.data)
        self.assertIn("Alice", body, "own tenant's employee should be visible")
        self.assertNotIn("Bob", body, "other tenant's employee must not be returned")

    def test_each_tenant_sees_a_disjoint_employee_set(self):
        """Symmetric check, so a filter that always returns A would fail."""
        seen = {}
        for username, expect, forbid in (
            ("tenant_a_user", "Alice", "Bob"),
            ("tenant_b_user", "Bob", "Alice"),
        ):
            client = APIClient()
            response = client.post(
                LOGIN_URL,
                {"username": username, "password": "secret123"},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
            listing = client.get(EMPLOYEE_LIST_URL)
            self.assertEqual(listing.status_code, 200, listing.data)
            body = str(listing.data)
            seen[username] = body
            self.assertIn(expect, body)
            self.assertNotIn(forbid, body, f"{username} saw the other tenant")
        self.assertNotEqual(
            seen["tenant_a_user"],
            seen["tenant_b_user"],
            "both tenants received identical payloads -- scoping is not applied",
        )


class UnplaceableApiUserTests(TestCase):
    """A valid token with no company must 403, not run unscoped querysets."""

    def tearDown(self):
        set_selected_company(None)

    def test_unplaceable_user_is_refused_not_unscoped(self):
        from rest_framework.exceptions import PermissionDenied
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.tokens import RefreshToken

        from horilla_api.authentication import TenantScopedJWTAuthentication

        stray = make_user("no_company_user", password="secret123")
        token = str(RefreshToken.for_user(stray).access_token)
        request = APIRequestFactory().get(
            EMPLOYEE_LIST_URL, HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        set_selected_company(None)

        with self.assertRaises(PermissionDenied):
            TenantScopedJWTAuthentication().authenticate(request)
        self.assertIsNone(get_selected_company())

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get(EMPLOYEE_LIST_URL)
        self.assertEqual(response.status_code, 403)

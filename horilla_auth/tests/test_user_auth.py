"""HorillaUser authentication smoke tests."""

from django.contrib.auth import authenticate
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user


class HorillaUserModelTests(TestCase):
    def setUp(self):
        # django-axes needs a request to attribute an attempt to a client; it
        # raises rather than silently skipping the check when one is missing.
        self.request = RequestFactory().post("/login/")

    def test_authenticate_rejects_inactive_user(self):
        user = make_user("auth_blocked", password="secret123")
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertIsNone(
            authenticate(self.request, username="auth_blocked", password="secret123")
        )

    def test_authenticate_rejects_bad_password(self):
        make_user("auth_badpw", password="secret123")
        self.assertIsNone(
            authenticate(self.request, username="auth_badpw", password="wrong")
        )


class LoginUserViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = make_company("Auth Co")
        self.password = "secret123"
        self.user = make_user("view_login", password=self.password)
        self.employee = make_employee(
            company=self.company,
            email="view_login@test.horilla",
            first_name="View",
            last_name="Login",
            user=self.user,
        )

    def test_login_success_redirects(self):
        response = self.client.post(
            reverse("login"),
            {"username": "view_login", "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_inactive_user_redirects_to_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("login"),
            {"username": "view_login", "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))

    def test_login_without_employee_redirects_to_login(self):
        orphan = make_user("no_emp", password=self.password)
        response = self.client.post(
            reverse("login"),
            {"username": "no_emp", "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotEqual(self.client.session.get("_auth_user_id"), str(orphan.pk))

"""
The capability payload a client paints its navigation from.

Two things it must get right: the role has to reflect what the user actually
is, and ``features`` has to state app availability explicitly -- a client
cannot infer it by probing, because DRF returns 404 both for a missing route
and a missing object.

These are UI hints. The tests assert the payload's shape and derivation, not
that it grants anything; authorization stays with the endpoints.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from horilla_api.api_methods.base.capabilities import build_capabilities

LOGIN_URL = "/api/v1/auth/login/"
CAPABILITIES_URL = "/api/v1/base/capabilities/"
PASSWORD = "secret123"


class CapabilitiesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Caps Co")

        self.user = make_user("caps_user", password=PASSWORD)
        self.employee = make_employee(
            company=self.company,
            email="caps@test.horilla",
            first_name="Cara",
            user=self.user,
        )

    def _login(self):
        response = self.client.post(
            LOGIN_URL,
            {"username": "caps_user", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_login_carries_capabilities(self):
        """The point of the change: no probe round trips before first paint."""
        caps = self._login()["capabilities"]
        self.assertIn("role", caps)
        self.assertIn("permissions", caps)
        self.assertIn("features", caps)
        self.assertIn("version", caps)

    def test_endpoint_returns_the_same_payload(self):
        """A long-lived client refreshes here rather than re-logging in."""
        from_login = self._login()["capabilities"]

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get(CAPABILITIES_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, from_login)

    def test_endpoint_requires_authentication(self):
        self.assertEqual(APIClient().get(CAPABILITIES_URL).status_code, 401)

    def test_plain_employee_is_employee(self):
        self.assertEqual(build_capabilities(self.user)["role"], "employee")
        self.assertFalse(build_capabilities(self.user)["permissions"]["view_team"])

    def test_reporting_manager_is_manager(self):
        report = make_employee(
            company=self.company,
            email="report@test.horilla",
            first_name="Ravi",
        )
        report.employee_work_info.reporting_manager_id = self.employee
        report.employee_work_info.save()

        caps = build_capabilities(self.user)
        self.assertEqual(caps["role"], "manager")
        self.assertTrue(caps["permissions"]["view_team"])

    def test_superuser_is_hrexec(self):
        admin = make_user("caps_admin", password=PASSWORD, is_superuser=True)
        self.assertEqual(build_capabilities(admin)["role"], "hrexec")

    def test_features_report_installed_apps_explicitly(self):
        features = build_capabilities(self.user)["features"]
        # geofencing/facedetection are installed from horilla_api/__init__.py,
        # not settings -- the manifest must still report them as present.
        self.assertTrue(features["geofencing"])
        self.assertTrue(features["facedetection"])
        self.assertTrue(features["leave"])
        self.assertTrue(all(isinstance(v, bool) for v in features.values()))

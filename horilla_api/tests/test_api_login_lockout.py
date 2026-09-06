"""
The API login must enforce the lockout, not merely count toward it.

AxesStandaloneBackend returns None for a locked-out caller rather than raising,
so the view's `invalid credentials` branch swallowed it: axes recorded six
failures while the endpoint kept answering 401, and an attacker could keep
guessing past the limit that stops the HTML login at five.
"""

from django.test import override_settings
from rest_framework.test import APITestCase

AXES_LIMIT = 4


def _reset_axes():
    from axes.handlers.proxy import AxesProxyHandler

    AxesProxyHandler.reset_attempts()
    AxesProxyHandler.reset_logs(age_days=None)


@override_settings(AXES_FAILURE_LIMIT=AXES_LIMIT)
class ApiLoginLockoutTests(APITestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)

    def _attempt(self, username="probe", password="wrong-password"):
        return self.client.post(
            "/api/v1/auth/login/",
            {"username": username, "password": password},
            format="json",
        )

    def test_failures_below_the_limit_return_401(self):
        for _ in range(AXES_LIMIT - 1):
            self.assertEqual(self._attempt().status_code, 401)

    def test_the_limit_switches_401_to_429(self):
        for _ in range(AXES_LIMIT - 1):
            self._attempt()

        # Counting without blocking is the bug: the endpoint has to start
        # refusing, not keep answering "invalid credentials" forever.
        self.assertEqual(self._attempt().status_code, 429)

    def test_lockout_persists_past_the_limit(self):
        for _ in range(AXES_LIMIT + 3):
            self._attempt()

        self.assertEqual(self._attempt().status_code, 429)

    def test_lockout_body_does_not_leak_whether_the_user_exists(self):
        for _ in range(AXES_LIMIT + 1):
            self._attempt()

        body = str(self._attempt().json())
        self.assertNotIn("probe", body)

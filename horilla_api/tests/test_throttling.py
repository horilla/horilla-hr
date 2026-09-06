"""Rate limits on the API.

django-axes locks an account after repeated *failed* passwords, but counts
nothing when the credentials are valid -- so a leaked password can be
replayed to mint tokens as fast as the server answers, and an authenticated
caller can hit any of the 681 API routes at any rate.

These pin the throttles that bound both, and pin the rates themselves: a
limit that quietly drifts to something meaningless is the usual way this
protection stops existing.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

LOGIN_URL = "/api/v1/auth/login/"


class ThrottleConfigurationTests(TestCase):
    """The wiring, independent of any request."""

    def test_throttle_classes_are_configured(self):
        from django.conf import settings

        classes = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
        self.assertIn("rest_framework.throttling.AnonRateThrottle", classes)
        self.assertIn("rest_framework.throttling.UserRateThrottle", classes)
        self.assertIn("rest_framework.throttling.ScopedRateThrottle", classes)

    def test_a_rate_exists_for_every_scope_in_use(self):
        """Each scope must be declared, even though the values are blanked
        under test.

        settings.base sets every rate to None when running the suite, so
        asserting the values here would only re-check that blanking. What
        matters is that no scope is missing from the mapping -- a scope with
        no entry raises ImproperlyConfigured on the first request that uses
        it, in production, not here.
        """
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("anon", "user", "login", "bulk"):
            with self.subTest(scope=scope):
                self.assertIn(scope, rates, f"no entry for the {scope} scope")

    def test_production_rates_are_real_values(self):
        """The rates the app actually ships with.

        Read from the settings module directly rather than from
        django.conf.settings, which the suite has blanked. Without this the
        real values are untested: a typo turning "12/min" into None would
        disable login throttling in production and no test would notice.
        """
        import re
        from pathlib import Path

        from django.conf import settings as dj_settings

        source = (
            Path(dj_settings.BASE_DIR) / "horilla" / "settings" / "base.py"
        ).read_text(encoding="utf-8")
        for scope in ("anon", "user", "login", "bulk"):
            with self.subTest(scope=scope):
                match = re.search(
                    rf'"{scope}": env\("THROTTLE_[A-Z]+", default="([^"]+)"\)',
                    source,
                )
                self.assertIsNotNone(
                    match, f"{scope} has no env-overridable default rate"
                )
                self.assertRegex(
                    match.group(1),
                    r"^\d+/(sec|min|hour|day)$",
                    f"{scope} default is not a valid DRF rate",
                )

    def test_login_view_carries_the_login_scope(self):
        """Without throttle_scope the view falls back to the anon rate, which
        is five times looser."""
        from horilla_api.api_views.auth.views import LoginAPIView

        self.assertEqual(getattr(LoginAPIView, "throttle_scope", None), "login")


class LoginThrottleTests(TestCase):
    """The login scope actually refuses once the rate is exceeded."""

    RATE = "3/min"  # small enough to trip inside a test

    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        # Throttle history lives in the cache; a leftover count from another
        # test would make this pass or fail for the wrong reason.
        cache.clear()

        # SimpleRateThrottle.THROTTLE_RATES is a *class attribute*, bound
        # from api_settings when rest_framework.throttling is imported.
        # override_settings reloads api_settings but cannot rebind an
        # attribute that was already read, so the decorator alone leaves the
        # throttle on the real 12/min rate and the test passes vacuously.
        # Patch the class attribute directly and restore it after.
        from rest_framework.throttling import SimpleRateThrottle

        self._throttle_cls = SimpleRateThrottle
        self._original_rates = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {
            **self._original_rates,
            "login": self.RATE,
        }
        self.company = make_company("Throttle Co")
        self.user = make_user("throttle_user", password="secret123")
        self.employee = make_employee(
            company=self.company, email="throttle@test.horilla", user=self.user
        )

    def tearDown(self):
        self._throttle_cls.THROTTLE_RATES = self._original_rates
        cache.clear()

    def _login(self):
        return self.client.post(
            LOGIN_URL,
            {"username": "throttle_user", "password": "secret123"},
            format="json",
        )

    def test_repeated_successful_logins_are_throttled(self):
        """Valid credentials, so axes never counts a failure -- the throttle
        is the only thing that stops this."""
        for i in range(3):
            self.assertEqual(
                self._login().status_code, 200, f"login {i + 1} should have succeeded"
            )

        self.assertEqual(
            self._login().status_code,
            429,
            "a fourth login inside the window was not throttled",
        )

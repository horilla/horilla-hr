"""
``/health/`` identifies the product without disclosing the release.

Mobile clients probe a user-typed host with this before posting credentials,
so that a wrong host reports "not a Horilla server" instead of "invalid
credentials". The endpoint must therefore stay unauthenticated and must carry
enough for that decision -- and no more.

The "no more" is the security half: this route is reachable by anyone, and the
project's published advisories name exact patched versions, so returning
``__version__`` here would let a scan map a host onto the advisories that
apply to it. That is what the second test guards.
"""

from django.test import TestCase

from horilla.__version__ import API_VERSION, __version__


class HealthVersionTests(TestCase):
    def test_health_is_unauthenticated_and_identifies_the_product(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "product": "horilla", "api": API_VERSION},
        )

    def test_health_does_not_disclose_the_release(self):
        """Regression guard: re-adding the version here is a scanner's gift."""
        body = self.client.get("/health/").content.decode()
        self.assertNotIn(
            __version__,
            body,
            "/health/ is unauthenticated; the exact release must not appear in "
            "it. Signed-in clients get the version from the capabilities "
            "payload instead.",
        )

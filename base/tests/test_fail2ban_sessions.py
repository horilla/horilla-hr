"""
Fail2BanMiddleware and log_login_failed: no session row per request, and a
client that keeps failing a login is still banned.
"""

from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse

from base import signals


class Fail2BanSessionTests(TestCase):
    def setUp(self):
        signals.failed_attempts.clear()
        signals.ban_time.clear()

    def tearDown(self):
        signals.failed_attempts.clear()
        signals.ban_time.clear()

    def test_requests_without_a_cookie_create_no_session(self):
        """
        Every request without a session cookie (health checks, devices,
        scripts) used to insert a django_session row. /health/ touches the
        session nowhere else, so any row here comes from the middleware.
        """
        for _ in range(3):
            self.client.cookies.clear()
            self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(Session.objects.count(), 0)

    def test_logged_out_pages_create_no_session(self):
        """
        login_required (function and class-based views) saved the page title
        before checking the login, and the breadcrumbs context processor
        saved a trail for every rendered page, the login page included.
        """
        for path in ("/", reverse("action-type-list"), "/login/"):
            self.client.cookies.clear()
            response = self.client.get(path, follow=True)
            self.assertEqual(response.status_code, 200, path)
            self.assertTemplateUsed(response, "login.html")
        self.assertEqual(Session.objects.count(), 0)

    @override_settings(FAIL2BAN_MAX_RETRY=2, FAIL2BAN_BAN_TIME=300)
    @patch.object(signals, "FAIL2BAN_LOG_ENABLED", True)
    def test_repeated_failed_logins_are_still_banned(self):
        # Straight to the POSTs: the failed-login handler has to create the
        # session the attempts are counted against.
        for _ in range(2):
            self.client.post("/login/", {"username": "nobody", "password": "wrong"})

        # One session from the first failed login on, carried by the client.
        self.assertEqual(Session.objects.count(), 1)
        self.assertEqual(len(signals.ban_time), 1)

        page = self.client.get("/login/")
        self.assertTemplateUsed(page, "403.html")

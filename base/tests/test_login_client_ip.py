"""
Login lockouts behind the Docker nginx use the real client IP.

axes locks the (username, IP) pair. Behind nginx every request arrived from
nginx's own address, so the pair was effectively the username alone: anyone
who could reach the login page could lock a real user out by failing five
times. And the previous X-Forwarded-For handling took the client-written
(left-most) value, so an attacker could also send a fresh address per attempt
and never be locked out.
"""

from unittest import mock

from axes.models import AccessAttempt
from django.test import TestCase, override_settings
from django.urls import reverse

from base.models import Company
from horilla.testkit import make_employee
from horilla_auth.models import HorillaUser

AXES_LIMIT = 3
NGINX = "172.19.0.3"


def _reset_axes():
    from axes.handlers.proxy import AxesProxyHandler

    AxesProxyHandler.reset_attempts()
    AxesProxyHandler.reset_logs(age_days=None)


@override_settings(
    AXES_FAILURE_LIMIT=AXES_LIMIT, HORILLA_TRUSTED_PROXIES=["172.16.0.0/12"]
)
class LoginClientIpTests(TestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)
        company = Company.objects.create(company="Acme", hq=True)
        self.user = HorillaUser.objects.create_user(
            username="alice", email="alice@test.horilla", password="correct-horse"
        )
        make_employee(company=company, email="alice@test.horilla", user=self.user)

    def _attempt(self, password, xff, remote=NGINX):
        self.client.logout()
        return self.client.post(
            reverse("login"),
            {"username": "alice", "password": password},
            REMOTE_ADDR=remote,
            HTTP_X_FORWARDED_FOR=xff,
            follow=True,
        )

    def test_the_failed_login_log_line_names_the_client_ip(self):
        with mock.patch("base.signals.FAIL2BAN_LOG_ENABLED", True), self.assertLogs(
            "django.security", "WARNING"
        ) as logs:
            self._attempt("wrong-password", "192.168.1.50")
        self.assertIn("from 192.168.1.50", logs.output[0])

    def test_a_failure_is_recorded_with_the_client_ip(self):
        self._attempt("wrong-password", "192.168.1.50")
        self.assertEqual(
            list(AccessAttempt.objects.values_list("ip_address", flat=True)),
            ["192.168.1.50"],
        )

    def test_a_spoofed_address_is_not_used(self):
        for fake in ("8.8.8.8", "9.9.9.9", "1.1.1.1"):
            self._attempt("wrong-password", f"{fake}, 192.168.1.50")
        self.assertEqual(
            list(AccessAttempt.objects.values_list("ip_address", flat=True)),
            ["192.168.1.50"],
        )
        # ...so rotating fake addresses still ends in a lockout.
        self.assertEqual(
            self._attempt("correct-horse", "192.168.1.50").status_code, 429
        )

    def test_a_lockout_from_one_ip_does_not_lock_out_another(self):
        for _ in range(AXES_LIMIT):
            self._attempt("wrong-password", "192.168.1.66")
        self.assertEqual(
            self._attempt("correct-horse", "192.168.1.66").status_code, 429
        )

        self._attempt("correct-horse", "192.168.1.50")
        self.assertIn("_auth_user_id", self.client.session)

    @override_settings(HORILLA_TRUSTED_PROXIES=[])
    def test_with_no_trusted_proxy_remote_addr_is_used(self):
        self._attempt("wrong-password", "192.168.1.50", remote="203.0.113.9")
        self.assertEqual(
            list(AccessAttempt.objects.values_list("ip_address", flat=True)),
            ["203.0.113.9"],
        )

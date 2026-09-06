"""
Login must lock out after repeated failures and must not leak account existence.

Before this, ``login_user`` accepted unlimited attempts -- no counter, no
lockout, no delay -- and nginx had no ``limit_req`` either, so there was no
rate limiting at any layer in front of an HR system holding salary and bank
details. It also answered "Access Denied: Your account is blocked." for a real
but inactive user and "Invalid username or password." otherwise, which
confirmed valid usernames to an unauthenticated caller.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from base.models import Company
from horilla.testkit import make_employee
from horilla_auth.models import HorillaUser

AXES_LIMIT = 3


def _reset_axes():
    from axes.handlers.proxy import AxesProxyHandler

    AxesProxyHandler.reset_attempts()
    AxesProxyHandler.reset_logs(age_days=None)


@override_settings(AXES_FAILURE_LIMIT=AXES_LIMIT, AXES_RESET_ON_SUCCESS=True)
class LoginLockoutTests(TestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)
        company = Company.objects.create(company="Acme", hq=True)
        self.user = HorillaUser.objects.create_user(
            username="alice", email="alice@test.horilla", password="correct-horse"
        )
        make_employee(company=company, email="alice@test.horilla", user=self.user)

    def _attempt(self, password):
        return self.client.post(
            reverse("login"),
            {"username": "alice", "password": password},
            follow=True,
        )

    def test_repeated_failures_lock_the_account_out(self):
        for _ in range(AXES_LIMIT):
            self._attempt("wrong-password")

        # The correct password must now be refused too -- a lockout that still
        # admits the right password stops nothing, since guessing is the attack.
        response = self._attempt("correct-horse")
        self.assertNotIn("_auth_user_id", self.client.session)
        # 429, not 403: axes reports the lockout as rate limiting, which is the
        # accurate status and matches what nginx returns for the same condition.
        self.assertEqual(response.status_code, 429)

    def test_successful_login_before_the_limit_still_works(self):
        self._attempt("wrong-password")
        self._attempt("wrong-password")

        self._attempt("correct-horse")

        self.assertIn("_auth_user_id", self.client.session)

    def test_success_resets_the_failure_counter(self):
        self._attempt("wrong-password")
        self._attempt("correct-horse")
        self.client.logout()

        # With the counter reset, a fresh run of failures must not trip the
        # lock early on the leftovers from before the success.
        for _ in range(AXES_LIMIT - 1):
            self._attempt("wrong-password")
        self._attempt("correct-horse")

        self.assertIn("_auth_user_id", self.client.session)


class LoginDoesNotLeakAccountExistenceTests(TestCase):
    def setUp(self):
        _reset_axes()
        self.addCleanup(_reset_axes)
        company = Company.objects.create(company="Acme", hq=True)
        blocked = HorillaUser.objects.create_user(
            username="blocked", email="blocked@test.horilla", password="pw-not-real"
        )
        make_employee(company=company, email="blocked@test.horilla", user=blocked)
        blocked.is_active = False
        blocked.save(update_fields=["is_active"])

    def _message_for(self, username):
        response = self.client.post(
            reverse("login"),
            {"username": username, "password": "whatever"},
            follow=True,
        )
        return [str(m) for m in response.context["messages"]]

    def test_blocked_and_unknown_accounts_give_the_same_message(self):
        self.assertEqual(
            self._message_for("blocked"),
            self._message_for("no-such-user-at-all"),
        )

"""
Expired sessions are deleted daily.

Django keeps expired sessions until `clearsessions` runs, and nothing in
Horilla ran it, so the table only grew (one install had 92,543 expired rows,
29% of its database).
"""

import importlib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.utils import timezone

from horilla.scheduling import get_registered_jobs


def make_session(expired=False):
    session = SessionStore()
    session["note"] = "kept until it expires"
    session.create()
    if expired:
        Session.objects.filter(session_key=session.session_key).update(
            expire_date=timezone.now() - timedelta(minutes=1)
        )
    return session.session_key


class ClearExpiredSessionsTests(TestCase):
    def test_expired_sessions_go_and_live_ones_stay(self):
        from base.scheduler import clear_expired_sessions

        live = make_session()
        make_session(expired=True)
        make_session(expired=True)

        with self.assertLogs("base.scheduler", level="INFO") as logs:
            clear_expired_sessions()

        self.assertEqual(
            list(Session.objects.values_list("session_key", flat=True)), [live]
        )
        self.assertIn("Cleared 2 expired sessions", logs.output[0])

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_an_engine_without_rows_is_left_alone(self):
        from base.scheduler import clear_expired_sessions

        make_session(expired=True)
        clear_expired_sessions()  # cookie sessions have nothing to clear
        self.assertEqual(Session.objects.count(), 1)

    def test_an_engine_that_cannot_clear_is_logged(self):
        from base.scheduler import clear_expired_sessions

        with patch.object(
            SessionStore, "clear_expired", side_effect=NotImplementedError
        ), self.assertLogs("base.scheduler", level="INFO") as logs:
            clear_expired_sessions()
        self.assertIn("cannot clear expired sessions", logs.output[0])

    def test_it_runs_daily(self):
        importlib.import_module("base.scheduler")
        job = next(
            j for j in get_registered_jobs() if j.job_id == "clear_expired_sessions"
        )
        self.assertEqual(job.trigger, "cron")
        self.assertEqual((job.kwargs["hour"], job.kwargs["minute"]), (3, 0))

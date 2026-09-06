"""
Request correlation and structured logging.

Before this there was no LOGGING config at all -- ~79 getLogger() call sites
falling through to Django's defaults, with gunicorn's plain-text access log as
the only production telemetry and nothing tying a log line to its request.
"""

import json
import logging

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from horilla.observability import (
    JSONFormatter,
    RequestIDFilter,
    RequestIDMiddleware,
    build_logging_config,
    get_request_id,
    set_request_id,
)


class RequestIDMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.addCleanup(set_request_id, None)

    def _run(self, request, capture):
        def view(req):
            capture["seen"] = get_request_id()
            from django.http import HttpResponse

            return HttpResponse("ok")

        return RequestIDMiddleware(view)(request)

    def test_generates_an_id_and_echoes_it(self):
        capture = {}
        response = self._run(self.factory.get("/"), capture)

        self.assertTrue(capture["seen"])
        self.assertEqual(response["X-Request-ID"], capture["seen"])

    def test_reuses_inbound_header_so_traces_stay_joined_up(self):
        capture = {}
        request = self.factory.get("/", headers={"x-request-id": "from-lb-123"})

        response = self._run(request, capture)

        self.assertEqual(capture["seen"], "from-lb-123")
        self.assertEqual(response["X-Request-ID"], "from-lb-123")

    def test_truncates_an_oversized_inbound_id(self):
        capture = {}
        request = self.factory.get("/", headers={"x-request-id": "A" * 5000})

        self._run(request, capture)

        # The value reaches the logs; an unbounded caller-supplied string is a
        # log-injection vector.
        self.assertLessEqual(len(capture["seen"]), 200)

    def test_context_is_cleared_after_the_response(self):
        self._run(self.factory.get("/"), {})

        # gthread workers reuse threads, so a value left behind would label the
        # next request's logs with this request's id.
        self.assertIsNone(get_request_id())

    def test_context_is_cleared_even_when_the_view_raises(self):
        def boom(_request):
            raise ValueError("kaboom")

        with self.assertRaises(ValueError):
            RequestIDMiddleware(boom)(self.factory.get("/"))

        self.assertIsNone(get_request_id())


class JSONFormatterTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(set_request_id, None)

    def _record(self, **kwargs):
        record = logging.LogRecord(
            name="probe",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg=kwargs.pop("msg", "hello %s"),
            args=kwargs.pop("args", ("world",)),
            exc_info=None,
        )
        for key, value in kwargs.items():
            setattr(record, key, value)
        RequestIDFilter().filter(record)
        return record

    def test_emits_one_json_object_per_record(self):
        payload = json.loads(JSONFormatter().format(self._record()))

        self.assertEqual(payload["level"], "WARNING")
        self.assertEqual(payload["logger"], "probe")
        self.assertEqual(payload["message"], "hello world")

    def test_carries_the_request_id(self):
        set_request_id("req-42")

        payload = json.loads(JSONFormatter().format(self._record()))

        self.assertEqual(payload["request_id"], "req-42")

    def test_request_id_is_a_placeholder_outside_a_request(self):
        payload = json.loads(JSONFormatter().format(self._record()))

        self.assertEqual(payload["request_id"], "-")

    def test_extra_keys_are_merged(self):
        payload = json.loads(
            JSONFormatter().format(self._record(employee_id=7, company="Acme"))
        )

        self.assertEqual(payload["employee_id"], 7)
        self.assertEqual(payload["company"], "Acme")

    def test_unserialisable_extra_falls_back_to_repr(self):
        payload = json.loads(JSONFormatter().format(self._record(obj=object())))

        # A logging call must never be the thing that breaks a request.
        self.assertIn("object", payload["obj"])


class LoggingConfigTests(SimpleTestCase):
    def test_json_in_production_readable_in_debug(self):
        self.assertEqual(
            build_logging_config(debug=False)["handlers"]["console"]["formatter"],
            "json",
        )
        self.assertEqual(
            build_logging_config(debug=True)["handlers"]["console"]["formatter"],
            "console",
        )

    def test_existing_loggers_are_not_disabled(self):
        # Third-party packages call getLogger() at import time, before this
        # config is applied; disabling them would silence them entirely.
        self.assertFalse(build_logging_config(debug=False)["disable_existing_loggers"])


class RequestIDEndToEndTests(TestCase):
    def test_response_carries_a_request_id_header(self):
        response = self.client.get(reverse("login"))

        self.assertTrue(response["X-Request-ID"])


class SentryScrubbingTests(SimpleTestCase):
    """
    Nothing sensitive may leave the process in a Sentry event.

    This is an HR system: a stack trace's local variables and a request's POST
    body can hold salaries, bank details, reset tokens and OTPs. Scrubbing
    happens here rather than relying on the receiving project's settings.
    """

    def setUp(self):
        self.addCleanup(set_request_id, None)

    def test_sensitive_keys_are_replaced(self):
        from horilla.observability import _before_send

        event = _before_send(
            {
                "request": {
                    "data": {
                        "username": "alice",
                        "password": "hunter2",
                        "account_number": "12345678",
                        "basic_pay": "90000",
                    }
                }
            },
            None,
        )

        data = event["request"]["data"]
        self.assertEqual(data["password"], "[scrubbed]")
        self.assertEqual(data["account_number"], "[scrubbed]")
        self.assertEqual(data["basic_pay"], "[scrubbed]")
        # Non-sensitive context must survive or the event is useless.
        self.assertEqual(data["username"], "alice")

    def test_scrubbing_reaches_nested_stack_frame_locals(self):
        from horilla.observability import _before_send

        event = _before_send(
            {
                "exception": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [{"vars": {"salary": "80000", "count": 3}}]
                            }
                        }
                    ]
                }
            },
            None,
        )

        frame = event["exception"]["values"][0]["stacktrace"]["frames"][0]
        self.assertEqual(frame["vars"]["salary"], "[scrubbed]")
        self.assertEqual(frame["vars"]["count"], 3)

    def test_partial_key_matches_are_caught(self):
        from horilla.observability import _before_send

        event = _before_send(
            {
                "extra": {
                    "employee_phone_number": "555",
                    "reset_token_value": "abc",
                    "home_address_line1": "1 Test St",
                }
            },
            None,
        )

        for key in event["extra"]:
            self.assertEqual(event["extra"][key], "[scrubbed]", key)

    def test_event_is_tagged_with_the_request_id(self):
        from horilla.observability import _before_send

        set_request_id("req-99")

        event = _before_send({"message": "boom"}, None)

        self.assertEqual(event["tags"]["request_id"], "req-99")

    def test_recursion_is_bounded(self):
        from horilla.observability import _before_send

        # A self-referential structure must not hang or blow the stack.
        node = {"salary": "1"}
        node["self"] = node

        self.assertIsNotNone(_before_send(node, None))


class SentryInitTests(SimpleTestCase):
    def test_no_dsn_means_no_initialisation(self):
        from horilla.observability import init_sentry

        # An open-source install must send nothing anywhere by default.
        self.assertFalse(init_sentry(dsn="", environment="test", release="0"))
        self.assertFalse(init_sentry(dsn=None, environment="test", release="0"))


class MetricsEndpointTests(TestCase):
    """
    /metrics reports on the background job runner.

    Phase 1 made the scheduler single-process, which removed the duplicate-run
    bug and created a single point of failure -- so whether it is alive is now
    worth scraping.
    """

    def setUp(self):
        from base.models import Company
        from horilla.testkit import make_employee
        from horilla_auth.models import HorillaUser

        company = Company.objects.create(company="Metrics Co", hq=True)
        self.staff = HorillaUser.objects.create_user(
            username="ops", email="ops@test.horilla", password="pw-not-real"
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        make_employee(company=company, email="ops@test.horilla", user=self.staff)

    def test_anonymous_callers_get_404(self):
        # Job counts and failure rates are operational detail, not public.
        self.assertEqual(self.client.get("/metrics/").status_code, 404)

    def test_staff_get_prometheus_text(self):
        self.client.force_login(self.staff)

        response = self.client.get("/metrics/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertIn("horilla_scheduler_jobs_registered", response.content.decode())

    def test_collection_failure_does_not_break_the_endpoint(self):
        from unittest.mock import patch

        self.client.force_login(self.staff)

        with patch(
            "django_apscheduler.models.DjangoJob.objects.count",
            side_effect=RuntimeError("db gone"),
        ):
            response = self.client.get("/metrics/")

        # A broken metric must not take down the scrape target.
        self.assertEqual(response.status_code, 200)


class ReadinessSchedulerTests(TestCase):
    """/ready/ reports the scheduler; it only 503s when required."""

    def test_ready_reports_missing_scheduler_without_failing(self):
        response = self.client.get("/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scheduler"], "missing")

    @override_settings(HORILLA_REQUIRE_SCHEDULER=True)
    def test_ready_fails_when_scheduler_is_required_and_missing(self):
        response = self.client.get("/ready/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["scheduler"], "missing")

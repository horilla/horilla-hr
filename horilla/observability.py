"""
Logging plumbing: request correlation and JSON output.

There were 79 ``getLogger()`` call sites and no ``LOGGING`` config at all, so
every one of them fell through to Django's defaults. In production that meant
gunicorn's plain-text access log was the only telemetry, and nothing tied a log
line to the request that produced it.

Two pieces here:

* ``RequestIDMiddleware`` puts an id on every request and echoes it back, so a
  user reporting an error can quote something greppable.
* ``RequestIDFilter`` + ``JSONFormatter`` get that id into the log records and
  emit one JSON object per line for log aggregators.

The formatter is hand-written rather than pulled from python-json-logger: it is
about twenty lines, and this runs on every log record in the process.
"""

from __future__ import annotations

import datetime as _datetime
import json
import logging
import uuid
from contextvars import ContextVar

# ContextVar, not thread-local: it survives async context switches, and each
# request gets its own value even when threads are reused (gunicorn runs gthread
# workers, so threads are very much reused).
_request_id: ContextVar[str | None] = ContextVar("horilla_request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_INBOUND_LENGTH = 200


def get_request_id() -> str | None:
    """The current request's id, or None outside a request."""
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


class RequestIDMiddleware:
    """
    Attach a correlation id to each request and return it in the response.

    Reuses an inbound ``X-Request-ID`` when present so a trace started at the
    load balancer stays joined up, but truncates it -- the value reaches the
    logs, and an unbounded caller-supplied string is a log-injection vector.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inbound = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = inbound.strip()[:_MAX_INBOUND_LENGTH] or uuid.uuid4().hex

        token = _request_id.set(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            # Same lifetime discipline as CompanyMiddleware: a value left on a
            # reused worker thread would label the next request's logs with the
            # previous request's id.
            _request_id.reset(token)


class RequestIDFilter(logging.Filter):
    """Make ``%(request_id)s`` usable in any formatter."""

    def filter(self, record):
        record.request_id = get_request_id() or "-"
        return True


class JSONFormatter(logging.Formatter):
    """
    One JSON object per line.

    ``extra={...}`` keys are merged in, so callers can attach structured context
    without a bespoke formatter per module.
    """

    _RESERVED = frozenset(
        vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
    ) | {"asctime", "message", "taskName"}

    def format(self, record):
        payload = {
            "timestamp": _datetime.datetime.fromtimestamp(
                record.created, tz=_datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or "-",
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in self._RESERVED or key in payload or key.startswith("_"):
                continue
            # Anything non-serialisable becomes its repr rather than raising --
            # a logging call must never be the thing that breaks a request.
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        return json.dumps(payload, default=str)


def build_logging_config(*, debug: bool, level: str = "INFO") -> dict:
    """
    Return a ``LOGGING`` dict: readable in DEBUG, JSON otherwise.

    Kept as a function so settings stays declarative and this is unit-testable
    without importing Django settings.
    """
    return {
        "version": 1,
        # Third-party packages call getLogger() at import time, before this
        # config is applied. Disabling those loggers would silence them.
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "horilla.observability.RequestIDFilter"},
        },
        "formatters": {
            "json": {"()": "horilla.observability.JSONFormatter"},
            "console": {
                "format": "[%(asctime)s] %(levelname)s %(name)s [%(request_id)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "filters": ["request_id"],
                "formatter": "console" if debug else "json",
            },
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Django logs every 4xx/5xx here; without an explicit entry it
            # inherits root and is fine, but pinning it documents the intent.
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            # Query logging is deafening and only ever wanted deliberately.
            "django.db.backends": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }


# ========================================
# ERROR TRACKING (Sentry)
# ========================================
# Inert unless SENTRY_DSN is set, so an open-source install sends nothing
# anywhere by default. This is an HR system: a stack trace's local variables can
# hold salaries, bank details and reset tokens, so PII is scrubbed on the way out
# rather than trusting the receiving project's settings.

# Substring matches against dict keys and form field names, lowercased. Drawn
# from the real model fields (employee/payroll/base) rather than a generic list.
_SENSITIVE_KEY_PARTS = (
    "account_number",
    "bank_name",
    "basic_pay",
    "salary",
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "authorization",
    "csrf",
    "otp",
    "dob",
    "date_of_birth",
    "emergency_contact",
    "ssn",
    "social_security",
    "tax_id",
    "phone",
    "address",
    "ifsc",
)

_SCRUBBED = "[scrubbed]"


def _is_sensitive_key(key) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _scrub(value, _depth=0):
    """Recursively replace sensitive values, leaving structure intact."""
    # Events nest deeply (frames -> vars -> objects); bail out rather than
    # risking recursion on a self-referential structure.
    if _depth > 12:
        return value
    if isinstance(value, dict):
        return {
            key: (_SCRUBBED if _is_sensitive_key(key) else _scrub(item, _depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub(item, _depth + 1) for item in value]
        return type(value)(scrubbed) if isinstance(value, tuple) else scrubbed
    return value


def _before_send(event, hint):
    """
    Scrub an outbound Sentry event and tag it with the request id.

    Drops the event entirely if scrubbing raises -- never ship something we
    could not clean.
    """
    try:
        scrubbed = _scrub(event)
        request_id = get_request_id()
        if request_id:
            # Joins the Sentry issue to the JSON log lines for the same request.
            scrubbed.setdefault("tags", {})["request_id"] = request_id
        return scrubbed
    except Exception:  # pragma: no cover - defensive
        return None


def init_sentry(*, dsn, environment, release, traces_sample_rate=0.0):
    """
    Initialise Sentry if a DSN is configured; otherwise do nothing.

    Returns True when Sentry was initialised, for the benefit of tests and
    startup logging.
    """
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:  # pragma: no cover - dependency is declared
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; skipping."
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[
            DjangoIntegration(),
            # Breadcrumbs from INFO, events only for ERROR -- WARNING-level
            # events would drown the project in routine validation noise.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Never attach usernames, emails or request bodies automatically.
        send_default_pii=False,
        before_send=_before_send,
        traces_sample_rate=traces_sample_rate,
    )

    return True


# ========================================
# METRICS
# ========================================
# Deliberately not django-prometheus: that wraps the database backend and adds
# two middlewares to every request for per-view latency histograms nobody has
# asked for yet. What is actually needed is whether the scheduler is alive and
# whether its jobs are running -- the thing Phase 1 just made single-process, and
# therefore a single point of failure.


def scheduler_metrics():
    """
    Prometheus text-format metrics for the background job runner.

    Reads django_apscheduler's own tables, so it reports on the scheduler
    process from whichever process is asked -- the web workers can serve this
    even though they no longer run jobs themselves.
    """
    import time

    lines = [
        "# HELP horilla_scheduler_jobs_registered Jobs currently in the jobstore.",
        "# TYPE horilla_scheduler_jobs_registered gauge",
    ]

    try:
        from django_apscheduler.models import DjangoJob, DjangoJobExecution

        job_count = DjangoJob.objects.count()
        lines.append(f"horilla_scheduler_jobs_registered {job_count}")

        # A scheduler that died leaves next_run_time in the past and drifting;
        # this is the number worth alerting on.
        overdue = DjangoJob.objects.filter(next_run_time__lt=time.time()).count()
        lines += [
            "# HELP horilla_scheduler_jobs_overdue Jobs whose next run time has passed.",
            "# TYPE horilla_scheduler_jobs_overdue gauge",
            f"horilla_scheduler_jobs_overdue {overdue}",
        ]

        statuses = DjangoJobExecution.objects.values_list("status", flat=True)
        counts: dict[str, int] = {}
        for status in statuses:
            counts[status] = counts.get(status, 0) + 1
        lines += [
            "# HELP horilla_scheduler_executions_total Job executions by status.",
            "# TYPE horilla_scheduler_executions_total counter",
        ]
        for status, count in sorted(counts.items()):
            lines.append(
                f'horilla_scheduler_executions_total{{status="{status}"}} {count}'
            )
    except Exception:  # pragma: no cover - metrics must never break the probe
        logging.getLogger(__name__).exception("Failed to collect scheduler metrics")
        lines.append("horilla_scheduler_jobs_registered 0")

    return "\n".join(lines) + "\n"

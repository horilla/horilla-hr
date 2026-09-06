"""horilla URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import logging

from django.conf import settings as django_settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import Http404, JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog

import notifications.urls

from . import settings

logger = logging.getLogger(__name__)


def health_check(request):
    """Liveness probe — cheap, no dependency checks (Docker HEALTHCHECK)."""
    return JsonResponse({"status": "ok"}, status=200)


def _scheduler_status():
    """ok if run_scheduler has written jobs; missing if that process never ran."""
    try:
        from django_apscheduler.models import DjangoJob

        return "ok" if DjangoJob.objects.exists() else "missing"
    except Exception:
        return "missing"


def readiness_check(request):
    """
    Readiness probe — verifies database (and Redis cache when REDIS_URL is set).

    Also reports whether the dedicated scheduler process has registered jobs.
    ``/health/`` stays a cheap liveness check (Docker HEALTHCHECK).

    The scheduler status is reported but does not fail the probe unless
    HORILLA_REQUIRE_SCHEDULER=1, which is off by default: a stopped scheduler
    delays background jobs, while a 503 here can remove web from the load
    balancer and stop the app serving requests entirely. Monitor the field;
    opt in to failing only where that trade-off is right.
    """
    checks = {}
    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        logger.exception("readiness probe: database unavailable")
        return JsonResponse(
            {"status": "unavailable", "database": "error"},
            status=503,
        )

    if getattr(settings, "REDIS_URL", None):
        try:
            cache.set("horilla_ready_probe", "1", timeout=5)
            if cache.get("horilla_ready_probe") != "1":
                raise RuntimeError("cache readback failed")
            checks["cache"] = "ok"
        except Exception as exc:
            return JsonResponse(
                {"status": "unavailable", "cache": str(exc), **checks},
                status=503,
            )

    checks["scheduler"] = _scheduler_status()
    if (
        getattr(django_settings, "HORILLA_REQUIRE_SCHEDULER", False)
        and checks["scheduler"] != "ok"
    ):
        return JsonResponse(
            {"status": "unavailable", **checks},
            status=503,
        )

    return JsonResponse({"status": "ok", **checks}, status=200)


def metrics(request):
    """
    Prometheus scrape endpoint for the background job runner.

    Staff-only. nginx also denies it from outside (see docker/nginx.conf) -- job
    counts and failure rates are operational detail, not public information, and
    `location /` would otherwise proxy this straight through.
    """
    from django.http import HttpResponse

    from horilla.observability import scheduler_metrics

    if not (request.user.is_authenticated and request.user.is_staff):
        raise Http404

    return HttpResponse(scheduler_metrics(), content_type="text/plain; version=0.0.4")


urlpatterns = [
    path("admin/", admin.site.urls),
    # django.contrib.auth.urls is here for the password_reset_* routes its forms
    # and mails reverse. Its /accounts/login/ renders registration/login.html,
    # which Horilla does not ship, so that one URL 500s — send it to the real
    # login page instead. (The include was also listed twice.)
    path(
        "accounts/login/",
        RedirectView.as_view(url=settings.LOGIN_URL, permanent=False),
        name="accounts-login-redirect",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("base.urls")),
    path("", include("horilla_automations.urls")),
    path("", include("horilla_views.urls")),
    path("", include("horilla_audit.urls")),
    path("", include("horilla_tour.urls")),
    path("employee/", include("employee.urls")),
    path("horilla-widget/", include("horilla_widgets.urls")),
    re_path(
        "^inbox/notifications/", include(notifications.urls, namespace="notifications")
    ),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("health/", health_check),
    path("ready/", readiness_check),
    path("metrics/", metrics),
]

# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

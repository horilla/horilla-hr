"""Subscription CRUD + delivery triggers for standard reports."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from horilla.decorators import login_required
from report.access import company_id_from_request, user_can_subscribe_report
from report.delivery import deliver_subscription
from report.models import ReportSubscription
from report.registry import get_report


def _owned_subscriptions(request):
    return ReportSubscription.objects.filter(owner=request.user).select_related(
        "company_id"
    )


def _reload_response(request):
    """Refresh the CBV list container in place, matching the rest of Horilla's
    'POST action -> click the hidden {view_id}Reload button' convention.
    Also closes #genericModal — a no-op for the row-action callers (toggle/
    delete/run-now, never invoked from inside that modal) but needed for the
    create-subscription form, which submits from inside it."""
    return HttpResponse(
        "<script>$('#reportSubscriptionsReload').click();"
        "$('#genericModal').removeClass('oh-modal--show');"
        "setTimeout(reloadMessage, 70);</script>"
    )


@login_required
@require_http_methods(["POST"])
def subscription_toggle(request, subscription_id):
    sub = get_object_or_404(_owned_subscriptions(request), pk=subscription_id)
    sub.is_active = not sub.is_active
    sub.save(update_fields=["is_active"])
    if request.headers.get("HX-Request"):
        return _reload_response(request)
    if request.headers.get("X-Requested-With"):
        return JsonResponse({"ok": True, "is_active": sub.is_active, "id": sub.id})
    messages.success(
        request,
        _("Schedule activated.") if sub.is_active else _("Schedule paused."),
    )
    return redirect("report-subscriptions")


@login_required
@require_http_methods(["POST", "DELETE"])
def subscription_delete(request, subscription_id):
    sub = get_object_or_404(_owned_subscriptions(request), pk=subscription_id)
    sub.delete()
    if request.headers.get("HX-Request"):
        return _reload_response(request)
    if request.headers.get("X-Requested-With"):
        return JsonResponse({"ok": True})
    messages.success(request, _("Schedule deleted."))
    return redirect("report-subscriptions")


@login_required
@require_http_methods(["POST"])
def subscription_run_now(request, subscription_id):
    sub = get_object_or_404(_owned_subscriptions(request), pk=subscription_id)
    definition = get_report(sub.report_slug)
    company_id = company_id_from_request(request)
    if definition and not user_can_subscribe_report(
        request.user, definition, company_id=company_id
    ):
        return HttpResponseForbidden(
            _("You do not have permission to run this report.")
        )

    result = deliver_subscription(sub, force=True)
    if result.ok:
        messages.success(request, result.detail or _("Report emailed."))
    else:
        messages.error(request, result.detail or _("Could not send schedule."))

    if request.headers.get("HX-Request"):
        return _reload_response(request)
    if request.headers.get("X-Requested-With"):
        return JsonResponse(
            {"ok": result.ok, "status": result.status, "detail": result.detail},
            status=200 if result.ok else 400,
        )
    return redirect("report-subscriptions")

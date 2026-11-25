"""
Views for the Firma e-signature integration: the candidate profile tab, the
send form, Refresh and Link actions, the settings page and the webhook.
"""

import json
import logging
import uuid

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from base.models import HorillaMailTemplate
from horilla.decorators import login_required, permission_required
from horilla.methods import handle_no_permission
from horilla_firma import services
from horilla_firma.accessibility import (
    SETTINGS_PERMISSION,
    can_link,
    can_send,
    can_view_requests,
)
from horilla_firma.firma_api import verify_webhook
from horilla_firma.forms import FirmaSettingsForm, SendForSignatureForm
from horilla_firma.models import (
    STATUS_UNCERTAIN,
    FirmaSettings,
    FirmaSignatureRequest,
    FirmaWebhookEvent,
)

logger = logging.getLogger(__name__)

MAX_WEBHOOK_BYTES = 1024 * 1024
TAB_TITLE = gettext_lazy("E-Signatures")


def register_profile_tabs():
    """Adds the E-Signatures tab to the candidate profile (once)."""
    from django.apps import apps

    if not apps.is_installed("recruitment"):
        return
    from recruitment.cbv.candidate_profile import CandidateProfileView

    if any(tab.get("view") is candidate_tab for tab in CandidateProfileView.tabs):
        return
    CandidateProfileView.add_tab(
        tab={
            "title": TAB_TITLE,
            "view": candidate_tab,
            "accessibility": "horilla_firma.accessibility.signature_tab_accessibility",
        }
    )


def _candidate(pk):
    from recruitment.models import Candidate

    # The company-scoped manager: a candidate of another company is not found.
    candidate = Candidate.objects.filter(pk=pk).first()
    if candidate is None:
        raise Http404
    return candidate


def _render_tab(request, candidate, result=None, status=200):
    # An interrupted send shows as an unknown outcome (with Link) at once.
    services.expire_stale_sends(candidate)
    records = FirmaSignatureRequest.objects.filter(candidate_id=candidate)
    return render(
        request,
        "horilla_firma/candidate_tab.html",
        {
            "candidate": candidate,
            "records": records,
            "result": result,
            "configured": bool(FirmaSettings.ready()),
            "can_send": can_send(request.user),
            "can_link": can_link(request.user),
            "uncertain_status": STATUS_UNCERTAIN,
        },
        status=status,
    )


@login_required
def candidate_tab(request, pk, **kwargs):
    """The E-Signatures tab: the candidate's signature requests."""
    candidate = _candidate(pk)
    if not can_view_requests(request, candidate):
        return handle_no_permission(request)
    return _render_tab(request, candidate)


@login_required
@permission_required("recruitment.change_candidate")
def send_form(request, pk):
    """The send form, with the Firma templates that can be sent to one candidate."""
    candidate = _candidate(pk)
    services.expire_stale_sends(candidate)
    config = FirmaSettings.ready()
    templates, complete, error = (
        services.list_send_templates(config) if config else ([], False, "")
    )
    return render(
        request,
        "horilla_firma/send_form.html",
        {
            "candidate": candidate,
            "configured": bool(config),
            "templates": templates,
            "templates_complete": complete,
            "templates_error": error,
            "mail_templates": HorillaMailTemplate.objects.all().order_by("title"),
            "send_token": uuid.uuid4().hex,
            "default_title": _("Offer letter for %(name)s") % {"name": candidate.name},
            "default_expiration_hours": (
                config.default_expiration_hours if config else None
            ),
            "has_uncertain": FirmaSignatureRequest.objects.filter(
                candidate_id=candidate, status=STATUS_UNCERTAIN
            ).exists(),
        },
    )


# Outermost, so the view keeps autocommit when a deployment sets
# ATOMIC_REQUESTS: the "sending" row must commit before Firma is called, and
# services.send refuses to send inside a transaction.
@transaction.non_atomic_requests
@login_required
@permission_required("recruitment.change_candidate")
@require_POST
def send_for_signature(request, pk):
    """Sends the chosen document to the candidate once, then shows the tab again."""
    candidate = _candidate(pk)
    form = SendForSignatureForm(request.POST)
    if not form.is_valid():
        result = services.Result(
            "error", _("The form is incomplete. Open it again and check the values.")
        )
        return _render_tab(request, candidate, result)
    data = form.cleaned_data
    mail_template = None
    if data["mode"] == "document":
        mail_template = HorillaMailTemplate.objects.filter(
            pk=data.get("mail_template")
        ).first()
        if mail_template is None:
            result = services.Result("error", _("Choose the offer letter template."))
            return _render_tab(request, candidate, result)
    result = services.send(
        request,
        candidate,
        {
            "mode": data["mode"],
            "template_id": data.get("template_id"),
            "mail_template": mail_template,
            "title": data.get("title"),
            "expiration_hours": data.get("expiration_hours"),
            "send_token": data["send_token"],
            "confirm_uncertain": data.get("confirm_uncertain"),
        },
    )
    return _render_tab(request, candidate, result)


def _record(pk):
    record = FirmaSignatureRequest.objects.filter(pk=pk).first()
    if record is None or record.candidate_id is None:
        raise Http404
    return record


@login_required
@permission_required("recruitment.change_candidate")
@require_POST
def refresh_request(request, pk):
    """Reads the request's status from Firma and fetches a missing signed PDF."""
    record = _record(pk)
    candidate = _candidate(record.candidate_id_id)
    return _render_tab(request, candidate, services.refresh(record))


@login_required
@permission_required(SETTINGS_PERMISSION)
@require_POST
def link_request(request, pk):
    """Records the Firma request behind a send whose outcome was unknown."""
    record = _record(pk)
    candidate = _candidate(record.candidate_id_id)
    result = services.link(record, request.POST.get("firma_id"))
    return _render_tab(request, candidate, result)


@login_required
@permission_required(SETTINGS_PERMISSION)
@require_http_methods(["GET", "POST"])
def settings_view(request):
    """The Firma settings page: credentials, Test connection, Register webhook."""
    config = FirmaSettings.current() or FirmaSettings()
    webhook_url = request.build_absolute_uri(reverse("firma-webhook"))
    form = FirmaSettingsForm(instance=config)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "test":
            _flash(request, services.test_connection(config))
            return redirect("firma-settings")
        if action == "register":
            if not config.pk:
                messages.error(request, _("Save the settings first."))
            else:
                _flash(request, services.register_webhook(config, webhook_url))
            return redirect("firma-settings")
        form = FirmaSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Firma settings saved."))
            return redirect("firma-settings")
    return render(
        request,
        "horilla_firma/settings.html",
        {
            "form": form,
            "config": config,
            "webhook_url": webhook_url,
            "has_api_key": bool(config.api_key_encrypted),
            "has_webhook_secret": bool(config.webhook_secret_encrypted),
            "enable_webhooks_notice": services.enable_webhooks_notice(),
        },
    )


def _flash(request, result):
    level = {"success": messages.SUCCESS, "warning": messages.WARNING}.get(
        result.level, messages.ERROR
    )
    messages.add_message(request, level, result.message)


def _reply(http_status, **body):
    return JsonResponse(body, status=http_status)


# Firma calls this without a session. Nothing is read from the payload or
# written until the HMAC signature over the raw body has been verified with
# the saved secret (fail closed without one).
@csrf_exempt
@require_POST
def webhook(request):
    """Receives Firma webhook events and answers quickly."""
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > MAX_WEBHOOK_BYTES:
        return _reply(413, error="payload too large")
    raw = request.body or b""
    if len(raw) > MAX_WEBHOOK_BYTES:
        return _reply(413, error="payload too large")

    config = FirmaSettings.current()
    secret = config.webhook_secret if config else ""
    outcome = verify_webhook(request.headers.get, raw, secret)
    if outcome != "ok":
        logger.info("Firma webhook refused: %s signature", outcome)
        return _reply(401, error="%s signature" % outcome)

    try:
        payload = json.loads(raw)
    except ValueError:
        return _reply(400, error="invalid JSON")
    event_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 140:
        return _reply(400, error="missing event id")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    signing_request = data.get("signing_request")
    signing_request = signing_request if isinstance(signing_request, dict) else {}
    # The event row and its status change commit together: an error rolls both
    # back and answers 500, so Firma's retry processes the event again.
    with transaction.atomic():
        try:
            with transaction.atomic():
                event = FirmaWebhookEvent.objects.create(
                    event_id=event_id,
                    event_type=str(payload.get("type") or "")[:140],
                    signing_request_id=str(signing_request.get("id") or "")[:64],
                )
        except IntegrityError:
            return _reply(200, status="duplicate")
        outcome = services.process_event(payload)
        if outcome not in ("updated", "unchanged"):
            # Not kept: the webhook is company wide, so events also arrive for
            # requests sent from elsewhere. Firma counts any answer other than
            # 2xx as a failed delivery, so these are acknowledged.
            event.delete()
    return _reply(200, status=outcome)

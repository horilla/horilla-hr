"""
Sending documents to Firma and applying what Firma reports back.

Send safety: a create-and-send is attempted at most once per submitted form.
The signature request row is written (status "sending") and committed before
the call to Firma, so a replayed or concurrent submission is refused, and the
outcome of a failed call is classified by firma_api.classify_create_and_send_failure:
only a definite refusal is reported as "nothing was sent"; anything else is
recorded as an unknown outcome that must be checked in Firma before sending
again.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.template import Context, Template
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from base.methods import (
    build_safe_template_request,
    generate_pdf,
    sanitize_mail_template_body,
)
from horilla_firma.firma_api import (
    ALREADY_SENT,
    EMAIL_PATTERN,
    INLINE_DOCUMENT_LIMIT,
    KEPT,
    NOT_CREATED,
    WEBHOOK_EVENTS,
    FirmaApiError,
    FirmaClient,
    build_document_body,
    build_template_body,
    classify_create_and_send_failure,
    encode_inline,
    pick_template_user,
    split_name,
    status_from_flags,
)
from horilla_firma.models import (
    SOURCE_DOCUMENT,
    SOURCE_TEMPLATE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_DECLINED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_RANK,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_UNCERTAIN,
    FirmaSettings,
    FirmaSignatureRequest,
)

logger = logging.getLogger(__name__)

# A "sending" row older than this was interrupted (the process stopped between
# writing the row and recording Firma's answer). The request may have been
# sent, so it becomes an unknown outcome.
SEND_STALE_AFTER = timedelta(minutes=5)

# Scheduled signed PDF downloads: each failure waits twice as long as the one
# before (15 minutes, then 30, ... at most one day), and the schedule stops
# after FETCH_MAX_ATTEMPTS failures. Refresh on the request tries again.
FETCH_FIRST_WAIT_MINUTES = 15
FETCH_MAX_WAIT_MINUTES = 24 * 60
FETCH_MAX_ATTEMPTS = 10
FETCH_BATCH = 50

WORD_STATUS = {
    "sent": STATUS_SENT,
    "in_progress": STATUS_IN_PROGRESS,
    "completed": STATUS_COMPLETED,
    "declined": STATUS_DECLINED,
    "cancelled": STATUS_CANCELLED,
    "expired": STATUS_EXPIRED,
}

EVENT_STATUS = {
    "signing_request.recipient.signed": "in_progress",
    "signing_request.completed": "completed",
    "signing_request.recipient.declined": "declined",
    "signing_request.cancelled": "cancelled",
    "signing_request.expired": "expired",
}

FIRMA_ID_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def enable_webhooks_notice():
    return _(
        "Firma delivers events to Horilla only when Enable Webhooks is on in the "
        "Firma dashboard (Settings, Webhook Configuration). It is off by default "
        "and cannot be changed through the API. Copy the Webhook Signing Secret "
        "from the same page into these settings. A test delivery from Firma is "
        "sent even when the switch is off, so a successful test does not prove "
        "that real events will arrive."
    )


class SendRefused(Exception):
    """A refusal before anything was sent to Firma."""


@dataclass
class Result:
    level: str  # "success", "warning" or "error"
    message: str
    record: FirmaSignatureRequest = None


def get_client(config=None):
    config = config or FirmaSettings.ready()
    if not config:
        raise SendRefused(
            _(
                "Firma e-signature is not set up. An administrator can set it up "
                "in Settings."
            )
        )
    return FirmaClient(config.api_key)


def _update(record, **fields):
    """Writes ``fields`` to the row without running model validation.

    Used after Firma has answered: a local failure must not raise, because
    raising would hide a request that may already be with the candidate.
    Returns True when the row was written.
    """
    try:
        with transaction.atomic():
            FirmaSignatureRequest.all_objects.filter(pk=record.pk).update(**fields)
    except Exception:
        logger.exception(
            "Firma signature request %s could not be updated (Firma id %s).",
            record.pk,
            fields.get("firma_id") or record.firma_id,
        )
        return False
    for key, value in fields.items():
        setattr(record, key, value)
    return True


def _parse_time(value):
    """A Firma ISO 8601 time as an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


# Building the document


def render_offer_letter_pdf(request, mail_template, candidate):
    """The offer letter PDF, rendered the way Send Mail attaches templates.

    Raises SendRefused when the PDF could not be made.
    """
    body = Template(sanitize_mail_template_body(mail_template.body))
    try:
        employee = request.user.employee_get
    except Exception:
        employee = None
    html = body.render(
        Context(
            {
                "instance": candidate,
                "self": employee,
                "request": build_safe_template_request(request),
            }
        )
    )
    response = generate_pdf(html, {}, path=False, title=mail_template.title)
    content = getattr(response, "content", b"") or b""
    if response.status_code != 200 or not content.startswith(b"%PDF"):
        raise SendRefused(_("The offer letter PDF could not be generated."))
    return content


def count_pdf_pages(content):
    """The page count of a PDF, or None when it cannot be read safely."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - PyMuPDF is in requirements.txt
        return None
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            count = document.page_count
    except Exception:
        return None
    return count if isinstance(count, int) and count > 0 else None


def _build_body(request, client, candidate, record, values, title, expiration):
    first_name, last_name = split_name(candidate.name)
    email = candidate.email.strip()
    if record.source == SOURCE_TEMPLATE:
        template_id = (values.get("template_id") or "").strip()
        if not template_id:
            raise SendRefused(_("Choose a Firma template."))
        # Read the template again: its roles may have changed since the form opened.
        template = client.get_template(template_id)
        if template is None:
            raise SendRefused(_("The Firma template no longer exists."))
        ok, user_or_message = pick_template_user(template)
        if not ok:
            raise SendRefused(user_or_message)
        _update(record, firma_template_name=str(template["name"])[:255])
        return build_template_body(
            template["id"],
            user_or_message,
            title,
            first_name,
            last_name,
            email,
            expiration,
        )

    mail_template = values.get("mail_template")
    if mail_template is None:
        raise SendRefused(_("Choose the offer letter template."))
    content = render_offer_letter_pdf(request, mail_template, candidate)
    page_count = count_pdf_pages(content)
    if len(content) <= INLINE_DOCUMENT_LIMIT:
        return build_document_body(
            title,
            first_name,
            last_name,
            email,
            page_count,
            document_b64=encode_inline(content),
            expiration_hours=expiration,
        )
    file_name = "%s.pdf" % (slugify(title)[:80] or "offer-letter")
    document_id = client.upload_document(file_name, content)
    return build_document_body(
        title,
        first_name,
        last_name,
        email,
        page_count,
        document_id=document_id,
        expiration_hours=expiration,
    )


# Sending


def expire_stale_sends(candidate=None):
    """Marks interrupted sends (of ``candidate``, or of everyone) as unknown.

    Runs when the tab or the send form opens, before a send, and in the
    scheduled job, so an interrupted send shows the "may have been sent"
    message and the Link action without waiting for the next send.
    """
    stale = FirmaSignatureRequest.all_objects.filter(
        status=STATUS_SENDING,
        created_at__lt=timezone.now() - SEND_STALE_AFTER,
    )
    if candidate is not None:
        stale = stale.filter(candidate_id=candidate)
    stale.update(
        status=STATUS_UNCERTAIN,
        message=_(
            "This send was interrupted before Firma's answer was recorded, so the "
            "signing request may have been sent. Check the Firma dashboard."
        ),
    )


def _inside_transaction():
    """True when the caller holds an open transaction (an atomic block).

    The send view opts out of ATOMIC_REQUESTS, so a send started by it is
    never inside one; tests that run inside Django's TestCase transaction
    replace this.
    """
    return transaction.get_connection().in_atomic_block


def _replayed(record):
    return Result(
        "warning",
        _(
            "This form was already submitted (%(title)s: %(status)s). Nothing was "
            "sent again."
        )
        % {"title": record.title, "status": record.get_status_display()},
        record,
    )


def send(request, candidate, values):
    """Sends a document to ``candidate`` through Firma, at most once per form.

    ``values``: mode ("template" or "document"), template_id or mail_template,
    title, expiration_hours, send_token (one per rendered form) and
    confirm_uncertain. Returns a Result; never raises for Firma errors.
    """
    if _inside_transaction():
        # Inside a caller's transaction the "sending" row below would not be
        # committed before the POST, so a concurrent send could not see it.
        logger.error(
            "Firma send refused: services.send was called inside a database "
            "transaction (rule: the pending row must commit before the POST)."
        )
        return Result(
            "error",
            _(
                "Horilla could not record this send before contacting Firma. "
                "Nothing was sent."
            ),
        )
    config = FirmaSettings.ready()
    if not config:
        return Result(
            "error",
            _(
                "Firma e-signature is not set up. An administrator can set it up "
                "in Settings."
            ),
        )
    token = str(values.get("send_token") or "").strip()[:64]
    if not token:
        return Result("error", _("This form has expired. Open it again."))
    existing = FirmaSignatureRequest.all_objects.filter(send_token=token).first()
    if existing:
        return _replayed(existing)

    expire_stale_sends(candidate)
    if (
        not values.get("confirm_uncertain")
        and FirmaSignatureRequest.all_objects.filter(
            candidate_id=candidate, status=STATUS_UNCERTAIN
        ).exists()
    ):
        return Result(
            "error",
            _(
                "An earlier send to this candidate may have been sent: Firma did not "
                "confirm it. Check the Firma dashboard first, then confirm below to "
                "send again."
            ),
        )

    email = (candidate.email or "").strip()
    if not (candidate.name or "").strip() or not EMAIL_PATTERN.match(email):
        return Result(
            "error",
            _("The candidate needs a name and a valid email address to sign."),
        )
    mode = values.get("mode")
    if mode not in (SOURCE_TEMPLATE, SOURCE_DOCUMENT):
        return Result("error", _("Choose what to send."))
    title = (str(values.get("title") or "").strip() or _("Offer letter"))[:255]
    expiration = values.get("expiration_hours") or config.default_expiration_hours

    mail_template = values.get("mail_template") if mode == SOURCE_DOCUMENT else None
    try:
        with transaction.atomic():
            record = FirmaSignatureRequest.all_objects.create(
                candidate_id=candidate,
                title=title,
                source=mode,
                firma_template_id=(
                    str(values.get("template_id") or "")[:64]
                    if mode == SOURCE_TEMPLATE
                    else ""
                ),
                mail_template_title=(
                    str(mail_template.title or "")[:255] if mail_template else ""
                ),
                mail_template_pk=mail_template.pk if mail_template else None,
                recipient_name=candidate.name[:255],
                recipient_email=email,
                status=STATUS_SENDING,
                send_token=token,
            )
    except IntegrityError:
        existing = FirmaSignatureRequest.all_objects.filter(send_token=token).first()
        if existing:
            return _replayed(existing)
        return Result(
            "error",
            _(
                "A document is already being sent to this candidate. Wait a moment "
                "and check again."
            ),
        )
    except ValidationError as error:
        return Result("error", " ".join(error.messages))

    # Everything before the POST: a failure here means nothing was sent.
    try:
        client = get_client(config)
        body = _build_body(
            request, client, candidate, record, values, title, expiration
        )
    except (SendRefused, FirmaApiError) as error:
        reason = error.message if isinstance(error, FirmaApiError) else str(error)
        message = _("%(reason)s Nothing was sent.") % {"reason": reason}
        _update(record, status=STATUS_FAILED, message=message)
        return Result("error", message, record)
    except Exception:
        # No create-and-send was attempted, so this too is a definite non-send.
        logger.exception("Firma send for request %s failed before sending", record.pk)
        message = _("The document could not be prepared. Nothing was sent.")
        _update(record, status=STATUS_FAILED, message=message)
        return Result("error", message, record)

    try:
        result = client.create_and_send(body)
    except Exception as error:  # Every failure is classified; none is retried.
        return _handle_send_failure(client, record, error)

    settings = (
        result.get("settings") if isinstance(result.get("settings"), dict) else {}
    )
    no_email = settings.get("send_signing_email") is False
    message = _("Sent for signature with Firma to %(name)s (%(email)s).") % {
        "name": record.recipient_name,
        "email": record.recipient_email,
    }
    if no_email:
        message += " " + _(
            "Firma did not email the invitation (the workspace or template "
            "turns it off)."
        )
    recorded = _update(
        record,
        status=STATUS_SENT,
        firma_id=str(result["id"])[:64],
        sent_at=timezone.now(),
        no_invitation_email=no_email,
        message=message,
    )
    if not recorded:
        return Result(
            "warning",
            _(
                "Firma sent signing request %(id)s, but Horilla could not record it. "
                "Do not send again; an administrator can link it on this tab."
            )
            % {"id": result["id"]},
        )
    return Result("success", message, record)


def _handle_send_failure(client, record, error):
    kind, firma_id = classify_create_and_send_failure(error)
    if kind == NOT_CREATED:
        reason = error.message if isinstance(error, FirmaApiError) else str(error)
        message = _("%(reason)s Nothing was sent.") % {"reason": reason}
        _update(record, status=STATUS_FAILED, message=message)
        return Result("error", message, record)

    if kind in (ALREADY_SENT, KEPT) and firma_id:
        other = (
            FirmaSignatureRequest.all_objects.filter(firma_id=firma_id)
            .exclude(pk=record.pk)
            .first()
        )
        if other:
            message = _(
                "Firma reports this signing request was already sent (%(id)s), and "
                "it is recorded as %(title)s. It was not sent again."
            ) % {"id": firma_id, "title": other.title}
            _update(record, status=STATUS_FAILED, message=message)
            return Result("warning", message, other)
        if kind == ALREADY_SENT:
            message = _(
                "Firma reports this signing request was already sent (%(id)s). It "
                "was not sent again."
            ) % {"id": firma_id}
        else:
            message = _(
                "Firma kept signing request %(id)s after an error, and it may already "
                "be with the candidate. Check it in Firma before sending again."
            ) % {"id": firma_id}
        _update(
            record,
            status=STATUS_SENT,
            firma_id=firma_id[:64],
            sent_at=timezone.now(),
            message=message,
        )
        if kind == ALREADY_SENT:
            _apply_remote_status(client, record)
        return Result("warning", message, record)

    # Unknown outcome: the request may have been created and sent. Never retry.
    logger.warning(
        "Firma create-and-send outcome unknown for signature request %s: %s",
        record.pk,
        getattr(error, "code", type(error).__name__),
    )
    message = _(
        "Firma did not confirm the result of this send, so the signing request may "
        "have been sent. Check the Firma dashboard before sending again. If Firma "
        "has it, an administrator can link it on this tab."
    )
    _update(record, status=STATUS_UNCERTAIN, message=message)
    return Result("warning", message, record)


def _apply_remote_status(client, record):
    """Best effort: reads the request from Firma and applies its status."""
    try:
        detail = client.get_signing_request(record.firma_id)
    except FirmaApiError:
        return False
    timestamps = detail.get("timestamps")
    timestamps = timestamps if isinstance(timestamps, dict) else {}
    word = status_from_flags(detail.get("status"))
    if not word:
        return False
    return apply_status(record, word, _parse_time(timestamps.get("finished_on")))


# Status from Firma


def apply_status(record, word, completed_at=None):
    """Moves ``record`` forward to the status ``word``. Returns True when it changed.

    The update only matches a row whose current status ranks lower, so two
    events racing each other can never move a request backwards.
    """
    status = WORD_STATUS.get(word)
    if not status:
        return False
    lower = [key for key, rank in STATUS_RANK.items() if rank < STATUS_RANK[status]]
    fields = {"status": status}
    if status == STATUS_COMPLETED:
        fields["completed_at"] = completed_at or timezone.now()
    changed = FirmaSignatureRequest.all_objects.filter(
        pk=record.pk, status__in=lower
    ).update(**fields)
    if changed:
        for key, value in fields.items():
            setattr(record, key, value)
    return bool(changed)


def process_event(payload):
    """Applies one verified webhook payload. Returns a short outcome word.

    Only the status changes here; the signed PDF is downloaded by the
    scheduled job, so the delivery is answered within Firma's 5 second limit.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    signing_request = data.get("signing_request")
    signing_request = signing_request if isinstance(signing_request, dict) else {}
    firma_id = signing_request.get("id")
    if not isinstance(firma_id, str) or not firma_id:
        return "ignored"
    record = FirmaSignatureRequest.all_objects.filter(firma_id=firma_id).first()
    if not record:
        return "unknown_request"
    word = EVENT_STATUS.get(payload.get("type"))
    if not word:
        return "unchanged"
    changed = apply_status(
        record, word, _parse_time(signing_request.get("completed_at"))
    )
    return "updated" if changed else "unchanged"


# Signed documents


def fetch_signed_document(record, config=None):
    """Downloads and stores the signed PDF. Returns True when it is stored."""
    if record.signed_document:
        return True
    try:
        content = get_client(config).fetch_signed_pdf(record.firma_id)
    except (FirmaApiError, SendRefused) as error:
        logger.info(
            "Firma signed document for request %s not fetched: %s (%s)",
            record.pk,
            getattr(error, "code", "NOT_CONFIGURED"),
            getattr(error, "status", ""),
        )
        return False
    file_name = "%s-signed.pdf" % (slugify(record.title)[:80] or "document")
    record.signed_document.save(file_name, ContentFile(content), save=False)
    return _update(
        record,
        signed_document=record.signed_document.name,
        fetch_attempts=0,
        next_fetch_at=None,
        fetch_stopped=False,
    )


def _fetch_failed(record):
    attempts = record.fetch_attempts + 1
    wait = min(FETCH_FIRST_WAIT_MINUTES * 2 ** (attempts - 1), FETCH_MAX_WAIT_MINUTES)
    stop = attempts >= FETCH_MAX_ATTEMPTS
    fields = {
        "fetch_attempts": attempts,
        "next_fetch_at": timezone.now() + timedelta(minutes=wait),
        "fetch_stopped": stop,
    }
    if stop:
        fields["message"] = _(
            "Firma did not deliver the signed document after %(count)s attempts, so "
            "Horilla stopped trying. Use Refresh to try again."
        ) % {"count": attempts}
        logger.warning(
            "Firma signed document for request %s: stopped after %s attempts.",
            record.pk,
            attempts,
        )
    _update(record, **fields)


def fetch_pending_signed_documents():
    """Scheduled: stores the signed PDFs of completed requests that lack one.

    Requests never tried come first, then the retries that are due. Each
    failure waits longer, so a request whose PDF cannot be fetched never holds
    back the others.
    """
    config = FirmaSettings.ready()
    if not config:
        return
    now = timezone.now()
    pending = (
        FirmaSignatureRequest.all_objects.filter(
            status=STATUS_COMPLETED, fetch_stopped=False, firma_id__isnull=False
        )
        .filter(Q(signed_document="") | Q(signed_document__isnull=True))
        .filter(Q(next_fetch_at__isnull=True) | Q(next_fetch_at__lte=now))
        .order_by(F("next_fetch_at").asc(nulls_first=True), "-created_at")
    )
    for record in pending[:FETCH_BATCH]:
        try:
            stored = fetch_signed_document(record, config)
        except Exception:
            logger.exception("Firma signed document fetch failed for %s", record.pk)
            stored = False
        if not stored:
            _fetch_failed(record)


def refresh(record):
    """Reads the request from Firma, applies its status, fetches a missing PDF."""
    if not record.firma_id:
        return Result("error", _("This request has no Firma signing request ID yet."))
    try:
        client = get_client()
        detail = client.get_signing_request(record.firma_id)
    except (FirmaApiError, SendRefused) as error:
        return Result("error", getattr(error, "message", str(error)))
    timestamps = detail.get("timestamps")
    timestamps = timestamps if isinstance(timestamps, dict) else {}
    word = status_from_flags(detail.get("status"))
    if word:
        apply_status(record, word, _parse_time(timestamps.get("finished_on")))
    record.refresh_from_db()
    if record.status == STATUS_COMPLETED and not record.signed_document:
        _update(record, fetch_attempts=0, next_fetch_at=None, fetch_stopped=False)
        if not fetch_signed_document(record):
            return Result(
                "warning",
                _(
                    "Signed in Firma. The signed document is not ready yet; it is "
                    "fetched automatically."
                ),
                record,
            )
    return Result(
        "success",
        _("Status from Firma: %(status)s.") % {"status": record.get_status_display()},
        record,
    )


def link(record, firma_id):
    """Records the Firma request behind a send whose outcome was unknown."""
    firma_id = (firma_id or "").strip()
    if not firma_id or len(firma_id) > 64 or set(firma_id) - FIRMA_ID_ALLOWED:
        return Result("error", _("Enter the Firma signing request ID."))
    if record.firma_id or record.status != STATUS_UNCERTAIN:
        return Result("error", _("Only a send with an unknown outcome can be linked."))
    if FirmaSignatureRequest.all_objects.filter(firma_id=firma_id).exists():
        return Result(
            "error",
            _("Firma signing request %(id)s is already recorded in Horilla.")
            % {"id": firma_id},
        )
    try:
        client = get_client()
        detail = client.get_signing_request(firma_id)
        users = client.get_signing_request_users(firma_id)
    except (FirmaApiError, SendRefused) as error:
        return Result("error", getattr(error, "message", str(error)))
    # The request must have been sent to this row's recipient (as a signer or
    # approver, not only in copy), or another person's signed document would
    # be stored on this candidate.
    expected = (record.recipient_email or "").strip().lower()
    emails = [
        str(user.get("email") or "").strip()
        for user in users
        if isinstance(user, dict) and user.get("designation") != "CC"
    ]
    if not expected or expected not in [email.lower() for email in emails]:
        return Result(
            "error",
            _(
                "Firma signing request %(id)s was not sent to %(email)s (its "
                "recipients: %(recipients)s), so it was not linked."
            )
            % {
                "id": firma_id,
                "email": record.recipient_email,
                "recipients": ", ".join(email for email in emails if email)
                or _("none"),
            },
        )
    timestamps = detail.get("timestamps")
    timestamps = timestamps if isinstance(timestamps, dict) else {}
    linked = _update(
        record,
        firma_id=firma_id,
        sent_at=_parse_time(timestamps.get("sent_on")),
        message=_("Linked to Firma signing request %(id)s.") % {"id": firma_id},
    )
    if not linked:
        return Result("error", _("The Firma signing request could not be linked."))
    apply_status(
        record,
        status_from_flags(detail.get("status")) or "sent",
        _parse_time(timestamps.get("finished_on")),
    )
    record.refresh_from_db()
    return Result(
        "success",
        _("Linked Firma signing request %(id)s. Its status is %(status)s.")
        % {"id": firma_id, "status": record.get_status_display()},
        record,
    )


# Settings actions


def test_connection(config):
    try:
        get_client(config).test_connection()
    except (FirmaApiError, SendRefused) as error:
        return Result("error", getattr(error, "message", str(error)))
    return Result("success", _("Connected to Firma."))


def list_send_templates(config):
    """Firma templates for the send form. Returns (templates, complete, error).

    Each template carries ``sendable`` and, when it cannot be sent to one
    candidate, ``reason``.
    """
    try:
        templates, complete = get_client(config).list_templates()
    except (FirmaApiError, SendRefused) as error:
        return [], False, getattr(error, "message", str(error))
    for template in templates:
        ok, user_or_message = pick_template_user(template)
        template["sendable"] = ok
        template["reason"] = "" if ok else user_or_message
    return templates, complete, ""


def register_webhook(config, url):
    """Registers the company webhook for ``url``, reusing one with the same URL."""
    if not config.webhook_secret:
        return Result(
            "error",
            _(
                "Save the Webhook Signing Secret from Firma (Settings, Webhook "
                "Configuration) first. Without it Horilla refuses every event Firma "
                "sends, and Firma disables a webhook after repeated failed deliveries."
            ),
        )
    if not url.startswith("https://"):
        return Result(
            "error",
            _(
                "Firma delivers webhooks to public HTTPS addresses only, and this "
                "address is %(url)s. Open these settings through the public HTTPS "
                "address of Horilla."
            )
            % {"url": url},
        )
    try:
        client = get_client(config)
        existing = [
            hook
            for hook in client.list_webhooks(url)
            if hook.get("url") == url and hook.get("id")
        ]
        if existing:
            webhook_id = existing[0]["id"]
            message = _reuse_webhook(client, existing[0])
        else:
            webhook_id = client.create_webhook(url)
            if not webhook_id:
                return Result("error", _("Firma did not return a webhook ID."))
            message = _("Registered the Firma webhook %(id)s.") % {"id": webhook_id}
    except (FirmaApiError, SendRefused) as error:
        return Result("error", getattr(error, "message", str(error)))
    FirmaSettings.objects.filter(pk=config.pk).update(webhook_id=str(webhook_id)[:64])
    return Result("success", message + " " + enable_webhooks_notice())


def _reuse_webhook(client, webhook):
    """An existing webhook for this address: re-enable it, add missing events.

    Firma disables a webhook by itself after repeated failed deliveries
    (``auto_disabled_at``), and a webhook created elsewhere may lack events.
    """
    events = webhook.get("events") if isinstance(webhook.get("events"), list) else []
    missing = [event for event in WEBHOOK_EVENTS if event not in events]
    disabled = webhook.get("enabled") is not True or bool(
        webhook.get("auto_disabled_at")
    )
    if not missing and not disabled:
        return _(
            "Firma already had an enabled webhook for Horilla (%(id)s); it is reused."
        ) % {"id": webhook["id"]}
    client.update_webhook(webhook["id"], {"enabled": True, "events": events + missing})
    if disabled:
        message = _(
            "The Firma webhook %(id)s was disabled and has been enabled again."
        ) % {"id": webhook["id"]}
    else:
        message = _("The Firma webhook %(id)s has been updated.") % {
            "id": webhook["id"]
        }
    if missing:
        message += " " + _("Events added: %(events)s.") % {"events": ", ".join(missing)}
    return message

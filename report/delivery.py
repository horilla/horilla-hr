"""
Scheduled / on-demand delivery of standard report subscriptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.core.mail import EmailMessage
from django.test import RequestFactory
from django.utils import timezone
from django.utils.translation import gettext as _

from base.backends import ConfiguredEmailBackend
from report.company_context import company_letterhead
from report.engine import filters_from_dict
from report.export import export_pdf, export_xlsx
from report.models import ReportRunLog, ReportSubscription
from report.registry import get_report, run_report

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    ok: bool
    status: str
    detail: str = ""


def subscription_is_due(subscription: ReportSubscription, now=None) -> bool:
    now = now or timezone.now()
    last = subscription.last_run_at
    if not last:
        return True
    delta = now - last
    if subscription.frequency == ReportSubscription.FREQUENCY_DAILY:
        return delta >= timedelta(hours=23)
    if subscription.frequency == ReportSubscription.FREQUENCY_WEEKLY:
        return delta >= timedelta(days=6, hours=12)
    if subscription.frequency == ReportSubscription.FREQUENCY_MONTHLY:
        return delta >= timedelta(days=28)
    return False


def _owner_request(subscription: ReportSubscription):
    """Minimal request for permission / export checks (no real HTTP session)."""
    factory = RequestFactory()
    request = factory.get("/")
    user = subscription.owner
    if user is None:
        return None
    request.user = user
    company_key = (
        str(subscription.company_id_id) if subscription.company_id_id else "all"
    )
    request.session = {"selected_company": company_key}
    return request


def _can_view_report(subscription: ReportSubscription, definition) -> bool:
    from report.access import user_can_view_report

    owner = subscription.owner
    if owner is None:
        return False
    return user_can_view_report(
        owner, definition, company_id=subscription.company_id_id
    )


def _can_export_report(subscription: ReportSubscription, definition) -> bool:
    from report.access import user_can_export_report

    request = _owner_request(subscription)
    if request is None:
        return False
    return user_can_export_report(
        subscription.owner,
        definition,
        request=request,
        company_id=subscription.company_id_id,
    )


def deliver_subscription(
    subscription: ReportSubscription,
    *,
    force: bool = False,
    update_last_run: bool = True,
) -> DeliveryResult:
    """
    Generate Excel for a subscription and email recipients.

    Re-checks view permission and export access at send time.
    """
    import report.metrics  # noqa: F401

    if not subscription.is_active and not force:
        return DeliveryResult(False, "inactive", "Subscription is inactive")

    now = timezone.now()
    if not force and not subscription_is_due(subscription, now):
        return DeliveryResult(False, "skipped", "Not due yet")

    claimed_from = subscription.last_run_at
    claimed = False

    definition = get_report(subscription.report_slug)
    if not definition:
        logger.warning(
            "Subscription %s references unknown report %s",
            subscription.id,
            subscription.report_slug,
        )
        return DeliveryResult(False, "missing_report", "Report definition unavailable")

    if not _can_view_report(subscription, definition):
        logger.info(
            "Skipping subscription %s — owner lacks view permission",
            subscription.id,
        )
        return DeliveryResult(False, "denied_view", "Owner lacks view permission")

    if not _can_export_report(subscription, definition):
        logger.info(
            "Skipping subscription %s — owner lacks export access",
            subscription.id,
        )
        return DeliveryResult(False, "denied_export", "Owner lacks export access")

    recipients = subscription.recipient_list()
    if not recipients:
        return DeliveryResult(False, "no_recipients", "No recipients configured")

    backend = ConfiguredEmailBackend()
    from_email = getattr(backend, "dynamic_from_email_with_display_name", None) or ""
    if not from_email:
        logger.warning(
            "Subscription %s skipped — email server not configured",
            subscription.id,
        )
        return DeliveryResult(False, "mail_unconfigured", "Email server not configured")

    # Claim the run before building the report, but after the cheap guards
    # above -- a subscription rejected for permissions or configuration must
    # stay unclaimed so it is re-evaluated next poll rather than looking as
    # though it had already been delivered.
    #
    # Duplicate execution across workers is now prevented upstream: jobs
    # register with horilla.scheduling and exactly one process
    # (manage.py run_scheduler) owns execution, rather than every gunicorn
    # worker starting its own BackgroundScheduler at import.
    #
    # This claim is kept as defence in depth, not as that fix. last_run_at
    # was written only *after* the mail was sent, so any second poller --
    # a stray scheduler, an operator running the management command by hand
    # while the service is up, a retry -- would pass the due check above and
    # send again. Claiming first makes delivery idempotent regardless of how
    # many pollers exist.
    #
    # A conditional UPDATE guarded on the value just read: exactly one
    # racer's write matches and the rest see 0 rows affected.
    # select_for_update is not an option here, since sqlite is the default
    # engine and treats it as a no-op.
    if update_last_run and not force:
        rows = ReportSubscription.objects.filter(
            pk=subscription.pk, last_run_at=claimed_from
        ).update(last_run_at=now)
        if not rows:
            return DeliveryResult(False, "skipped", "Already claimed by another worker")
        subscription.last_run_at = now
        claimed = True

    try:
        filters = filters_from_dict(
            subscription.filters or {},
            default_company_id=subscription.company_id_id,
        )
        filters.extra["row_limit"] = 5000
        payload = run_report(subscription.report_slug, filters)
        company = company_letterhead(
            company_id=filters.company_id or subscription.company_id_id
        )
        filters_pairs = filters.summary_pairs()
        meta = {
            "product_name": "Horilla HR · Standard Reports",
            "company": company,
            "user": (
                str(subscription.owner)
                if subscription.owner_id
                else "Scheduled delivery"
            ),
            "slug": subscription.report_slug,
            "domain": getattr(definition, "domain", ""),
            "filters_pairs": filters_pairs,
            "filters_label": " · ".join(
                value if label == "Period" else f"{label}: {value}"
                for label, value in filters_pairs
            ),
            "generated_at": now,
        }
        fmt = (
            (subscription.filters or {}).get("format")
            or filters.extra.get("format")
            or "xlsx"
        )
        fmt = str(fmt).lower()
        if fmt == "pdf":
            response = export_pdf(
                payload,
                filename=f"{subscription.report_slug}.pdf",
                meta=meta,
            )
            attach_name = f"{subscription.report_slug}.pdf"
            attach_type = "application/pdf"
        else:
            response = export_xlsx(
                payload,
                filename=f"{subscription.report_slug}.xlsx",
                meta=meta,
            )
            attach_name = f"{subscription.report_slug}.xlsx"
            attach_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        report_title = str(definition.name)
        body = (
            f"{_('Attached is your scheduled Horilla report:')}\n\n"
            f"{report_title}\n"
            f"{_('Period')}: {filters.from_date} → {filters.to_date}\n"
            f"{_('Subscription')}: {subscription.name}\n"
            f"{_('Format')}: {fmt.upper()}\n"
        )
        email = EmailMessage(
            subject=f"[Horilla] {subscription.name}",
            body=body,
            from_email=from_email,
            to=recipients,
            connection=backend,
        )
        email.attach(attach_name, response.content, attach_type)
        sent = email.send(fail_silently=False)
        if not sent:
            # Hand the slot back so the next poll retries instead of waiting
            # a whole frequency interval for a send that never happened.
            _release_claim(subscription, claimed_from, claimed)
            return DeliveryResult(False, "send_failed", "Mail backend returned 0")

        if update_last_run and force:
            # Forced runs skip the claim above, so stamp them here.
            subscription.last_run_at = now
            subscription.save(update_fields=["last_run_at"])

        try:
            ReportRunLog.objects.create(
                report_slug=subscription.report_slug,
                action=ReportRunLog.ACTION_SUBSCRIBE,
                filters=subscription.filters or {},
                user=subscription.owner,
                company_id_id=subscription.company_id_id,
            )
        except Exception:
            logger.exception(
                "Could not write run log for subscription %s", subscription.id
            )

        logger.info("Sent report subscription %s to %s", subscription.id, recipients)
        return DeliveryResult(True, "sent", f"Sent to {', '.join(recipients)}")
    except Exception as exc:
        logger.exception("Failed report subscription %s", subscription.id)
        _release_claim(subscription, claimed_from, claimed)
        return DeliveryResult(False, "error", str(exc))


def _release_claim(subscription, previous_last_run, was_claimed: bool) -> None:
    """Undo the run claim so a failed delivery is retried next poll.

    Only rolls back if this process still holds the claim, so a later
    successful run by another worker is never clobbered.
    """
    if not was_claimed:
        return
    try:
        ReportSubscription.objects.filter(
            pk=subscription.pk, last_run_at=subscription.last_run_at
        ).update(last_run_at=previous_last_run)
        subscription.last_run_at = previous_last_run
    except Exception:
        logger.exception(
            "Could not release run claim for subscription %s", subscription.id
        )


def run_due_subscriptions(*, force_id: Optional[int] = None) -> list[DeliveryResult]:
    """Process due subscriptions, or a single forced id."""
    results: list[DeliveryResult] = []
    if force_id:
        try:
            sub = ReportSubscription.objects.get(pk=force_id)
        except ReportSubscription.DoesNotExist:
            return [DeliveryResult(False, "not_found", f"id={force_id}")]
        results.append(deliver_subscription(sub, force=True))
        return results

    qs = ReportSubscription.objects.filter(is_active=True).select_related(
        "owner", "company_id"
    )
    for sub in qs.iterator():
        results.append(deliver_subscription(sub, force=False))
    return results

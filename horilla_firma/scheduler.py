"""
Background jobs for the Firma e-signature integration, run by
``manage.py run_scheduler`` (see horilla/scheduling.py).
"""

from datetime import timedelta

from django.utils import timezone

from horilla.scheduling import register_job

# Firma retries one event for about an hour (3 attempts), so de-duplication
# rows are kept far longer than any retry can arrive.
EVENT_RETENTION_DAYS = 14


def fetch_pending_signed_documents():
    """Stores the signed PDFs of completed requests (the webhook never downloads)."""
    from horilla_firma.services import fetch_pending_signed_documents as fetch

    fetch()


def expire_interrupted_sends():
    """Shows interrupted sends as an unknown outcome (they may have been sent)."""
    from horilla_firma.services import expire_stale_sends

    expire_stale_sends()


def delete_old_webhook_events():
    from horilla_firma.models import FirmaWebhookEvent

    cutoff = timezone.now() - timedelta(days=EVENT_RETENTION_DAYS)
    FirmaWebhookEvent.objects.filter(received_at__lt=cutoff).delete()


register_job(fetch_pending_signed_documents, "interval", minutes=5)
register_job(expire_interrupted_sends, "interval", minutes=5)
register_job(delete_old_webhook_events, "interval", days=1)

"""
scheduler.py

Daily purge of the SCIM request log. Run by ``manage.py run_scheduler``, which
imports every app's scheduler module, rather than on every SCIM request.
"""

from datetime import timedelta

from django.utils import timezone

from horilla.scheduling import register_job

EVENT_RETENTION = timedelta(days=30)


def purge_old_events():
    from horilla_scim.models import ScimEvent

    ScimEvent.objects.filter(created_at__lt=timezone.now() - EVENT_RETENTION).delete()


register_job(purge_old_events, "interval", hours=24)

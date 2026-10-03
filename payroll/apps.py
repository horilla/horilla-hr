"""
App configuration for the 'payroll' app.
"""

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


class PayrollConfig(AppConfig):
    """
    AppConfig for the 'payroll' app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"

    def ready(self) -> None:
        ready = super().ready()
        from django.urls import include, path

        from horilla.urls import urlpatterns
        from payroll import scheduler, signals

        settings.APPS.append("payroll")
        urlpatterns.append(
            path("payroll/", include("payroll.urls.urls")),
        )

        # The standard pay items create themselves. On post_migrate rather
        # than here in ready(): touching the database during app loading is
        # what the RuntimeWarning at startup is about, and on a fresh database
        # the tables do not exist yet. Idempotent on system_key, so it costs
        # one query per kind per migrate and never overwrites a stored
        # setting. See payroll/system_components.py.
        from django.db.models.signals import post_migrate

        post_migrate.connect(seed_system_components, sender=self)
        return ready


def seed_system_components(sender, **kwargs):
    """Create any standard pay item that does not exist yet."""
    import logging

    from payroll.system_components import seed

    try:
        created = seed()
    except Exception:  # a partially migrated database, say
        logging.getLogger(__name__).exception(
            "Could not seed the standard payroll components"
        )
        return
    if created:
        logging.getLogger(__name__).info(
            "Created %s standard payroll component(s)", len(created)
        )

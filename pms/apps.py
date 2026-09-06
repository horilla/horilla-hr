"""
Django application configuration for the PMS (Performance Management System) app.
"""

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class PmsConfig(AppConfig):
    """
    This class provides configuration settings for the PMS app, such as the default
    database field type and the app's name.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "pms"
    verbose_name = _("Performance")

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        settings.APPS.append("pms")
        urlpatterns.append(
            path("pms/", include("pms.urls")),
        )

        from horilla_views.related_link_registry import register_detail_view
        from pms.models import QuestionTemplate

        register_detail_view(QuestionTemplate, get_url=QuestionTemplate.get_related_url)

        super().ready()
        try:
            from pms.signals import start_automation

            start_automation()
        except:
            """
            Migrations are not affected yet
            """

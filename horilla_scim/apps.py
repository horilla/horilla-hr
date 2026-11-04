from django.apps import AppConfig
from django.conf import settings


class HorillaScimConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "horilla_scim"
    verbose_name = "SCIM Provisioning"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        settings.APPS.append("horilla_scim")
        urlpatterns.append(
            path("", include("horilla_scim.urls")),
        )
        from horilla_scim import sidebar  # noqa: F401

        super().ready()

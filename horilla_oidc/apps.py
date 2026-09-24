from django.apps import AppConfig
from django.conf import settings


class HorillaOidcConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "horilla_oidc"
    verbose_name = "OIDC SSO"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        settings.APPS.append("horilla_oidc")
        urlpatterns.append(
            path("", include("horilla_oidc.urls")),
        )
        super().ready()

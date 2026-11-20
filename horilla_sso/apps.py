from django.apps import AppConfig
from django.conf import settings


class HorillaSsoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "horilla_sso"
    verbose_name = "Single Sign-On"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        settings.APPS.append("horilla_sso")
        urlpatterns.append(path("", include("horilla_sso.urls")))
        super().ready()

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HorillaFirmaConfig(AppConfig):
    """
    Optional Firma e-signature integration.

    Nothing is sent and no tab is shown until an administrator switches it on
    and saves a Firma API key under Settings, Integrations, Firma E-Signature.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "horilla_firma"
    verbose_name = _("Firma E-Signature")

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns
        from horilla_firma import sidebar  # noqa: F401  (Settings menu entry)
        from horilla_firma.views import register_profile_tabs

        urlpatterns.append(path("firma/", include("horilla_firma.urls")))
        register_profile_tabs()
        super().ready()

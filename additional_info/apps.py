from django.apps import AppConfig
from django.conf import settings


class AdditionalInfoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "additional_info"
    verbose_name = "Additional Info"

    def ready(self):
        from django.db.models.signals import post_delete, post_save
        from django.urls import include, path

        from additional_info import importing
        from additional_info.models import AdditionalInfoField
        from horilla.urls import urlpatterns

        # The import keeps its list of columns for a moment; a changed field must show up in it at once.
        for signal in (post_save, post_delete):
            signal.connect(
                lambda **kwargs: importing.forget(),
                sender=AdditionalInfoField,
                weak=False,
            )

        settings.APPS.append("additional_info")
        urlpatterns.append(path("", include("additional_info.urls")))
        super().ready()

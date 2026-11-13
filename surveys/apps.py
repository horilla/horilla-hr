from django.apps import AppConfig
from django.conf import settings


class SurveysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "surveys"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        settings.APPS.append("surveys")
        urlpatterns.append(path("surveys/", include("surveys.urls")))
        super().ready()

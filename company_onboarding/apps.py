from django.apps import AppConfig
from django.conf import settings


class CompanyOnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "company_onboarding"
    verbose_name = "Company Setup"

    def ready(self):
        from django.urls import include, path

        from horilla.urls import urlpatterns

        from company_onboarding import signals  # noqa: F401

        settings.APPS.append("company_onboarding")
        urlpatterns.append(
            path("company-onboarding/", include("company_onboarding.urls")),
        )
        super().ready()

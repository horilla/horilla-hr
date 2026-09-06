from django.conf import settings
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from horilla_api.schema import OrderedTagSchemaGenerator

# Create schema view for Swagger and ReDoc
schema_view = get_schema_view(
    openapi.Info(
        title="Horilla API",
        default_version="v1",
        description="API documentation for Horilla HRMS. Click the 'Authorize' button at the top to authenticate.",
        terms_of_service="https://www.horilla.com/terms/",
        contact=openapi.Contact(email="support@horilla.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=settings.DEBUG,
    permission_classes=(
        (permissions.AllowAny,) if settings.DEBUG else (permissions.IsAdminUser,)
    ),
    generator_class=OrderedTagSchemaGenerator,
)

urlpatterns = [
    # API Documentation URLs
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("docs/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-docs"),
    # API Endpoints (static configuration)
    path("auth/", include("horilla_api.api_urls.auth.urls")),
    path("asset/", include("horilla_api.api_urls.asset.urls")),
    path("base/", include("horilla_api.api_urls.base.urls")),
    path("employee/", include("horilla_api.api_urls.employee.urls")),
    path("notifications/", include("horilla_api.api_urls.notifications.urls")),
    path("payroll/", include("horilla_api.api_urls.payroll.urls")),
    path("attendance/", include("horilla_api.api_urls.attendance.urls")),
    path("leave/", include("horilla_api.api_urls.leave.urls")),
    path("helpdesk/", include("horilla_api.api_urls.helpdesk.urls")),
    path("project/", include("horilla_api.api_urls.project.urls")),
    path("onboarding/", include("horilla_api.api_urls.onboarding.urls")),
    path("offboarding/", include("horilla_api.api_urls.offboarding.urls")),
    path("recruitment/", include("horilla_api.api_urls.recruitment.urls")),
    path("pms/", include("horilla_api.api_urls.pms.urls")),
]

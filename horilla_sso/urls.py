"""Single sign-on routes. The Microsoft paths and names are kept as they were first registered with Azure."""

from django.urls import path

from horilla_sso import views

urlpatterns = [
    path(
        "login/microsoft/",
        views.sso_login,
        {"provider": "microsoft"},
        name="microsoft-sso-login",
    ),
    path(
        "login/microsoft/callback/",
        views.sso_callback,
        {"provider": "microsoft"},
        name="microsoft-sso-callback",
    ),
    path(
        "settings/microsoft-sso/",
        views.sso_settings,
        {"provider": "microsoft"},
        name="microsoft-sso-settings",
    ),
    path(
        "login/google/",
        views.sso_login,
        {"provider": "google"},
        name="google-sso-login",
    ),
    path(
        "login/google/callback/",
        views.sso_callback,
        {"provider": "google"},
        name="google-sso-callback",
    ),
    path(
        "settings/google-sso/",
        views.sso_settings,
        {"provider": "google"},
        name="google-sso-settings",
    ),
]

"""
urls.py

This module is used to map url path with view methods.
"""

from django.urls import path

from horilla_oidc import views

urlpatterns = [
    path("accounts/sso/<slug:slug>/login/", views.sso_login, name="oidc_login"),
    path("accounts/sso/<slug:slug>/callback/", views.sso_callback, name="oidc_callback"),
    path("settings/oidc-settings/", views.oidc_settings_view, name="oidc-settings"),
]

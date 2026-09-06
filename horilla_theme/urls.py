"""
URLs for the horilla_theme app
"""

from django.urls import path

from . import views

app_name = "horilla_theme"

urlpatterns = [
    # Define your URL patterns here
    path("color-theme-view/", views.ThemeView.as_view(), name="color_theme_view"),
    path("change-theme/", views.ChangeThemeView.as_view(), name="change_theme"),
    path("set-default/", views.SetDefaultThemeView.as_view(), name="set_default_theme"),
]

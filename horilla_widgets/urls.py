"""
horilla_widget/urls.py
"""

from django.urls import path

from horilla_widgets import views

urlpatterns = [
    path("get-filter-form/", views.get_filter_form, name="get-filter-form"),
    path(
        "ajax-choices/<str:field_key>/",
        views.ajax_select_choices,
        name="horilla-ajax-choices",
    ),
]

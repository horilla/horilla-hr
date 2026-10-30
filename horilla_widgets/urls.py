"""
horilla_widget/urls.py
"""

from django.urls import path

from horilla_widgets import views

urlpatterns = [
    path(
        "ajax-choices/<str:field_key>/",
        views.ajax_select_choices,
        name="horilla-ajax-choices",
    ),
    path(
        "employee-picker-ids/",
        views.employee_picker_ids,
        name="employee-picker-ids",
    ),
    path(
        "employee-picker-rows/",
        views.employee_picker_rows,
        name="employee-picker-rows",
    ),
]

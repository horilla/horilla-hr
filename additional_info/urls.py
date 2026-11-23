"""Additional info routes."""

from django.urls import path

from additional_info.cbv import fields, section

urlpatterns = [
    path(
        "additional-info/section/<int:pk>/",
        section.additional_info_section,
        name="additional-info-section",
    ),
    path(
        "additional-info/fields-tab/",
        fields.fields_tab,
        name="additional-info-fields-tab",
    ),
    path(
        "additional-info/field-list/",
        fields.AdditionalInfoFieldListView.as_view(),
        name="additional-info-field-list",
    ),
    path(
        "additional-info/field-navbar/",
        fields.AdditionalInfoFieldNavView.as_view(),
        name="additional-info-field-navbar",
    ),
    path(
        "additional-info/field-create-form/",
        fields.AdditionalInfoFieldFormView.as_view(),
        name="additional-info-field-create-form",
    ),
    path(
        "additional-info/field-update-form/<int:pk>/",
        fields.AdditionalInfoFieldFormView.as_view(),
        name="additional-info-field-update-form",
    ),
    path(
        "additional-info/field-delete/<int:pk>/",
        fields.delete_field,
        name="additional-info-field-delete",
    ),
]

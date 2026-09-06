"""
horilla_views/urls.py
"""

from django.urls import path

from horilla_views import views
from horilla_views.generic.cbv import history
from horilla_views.generic.cbv.views import (
    HorillaListView,
    ReloadMessages,
    dispatch_profile_tab,
)

urlpatterns = [
    path("toggle-columns/", views.ToggleColumn.as_view(), name="toggle-columns"),
    path("active-tab/", views.ActiveTab.as_view(), name="active-tab"),
    path("active-group/", views.ActiveGroup.as_view(), name="cbv-active-group"),
    path("reload-field/", views.ReloadField.as_view(), name="reload-field"),
    path("reload-messages/", ReloadMessages.as_view(), name="reload-messages"),
    path("saved-filter/", views.SavedFilter.as_view(), name="saved-filter"),
    path(
        "saved-filter/<int:pk>/",
        views.SavedFilter.as_view(),
        name="saved-filter-update",
    ),
    path(
        "delete-saved-filter/<int:pk>/",
        views.DeleteSavedFilter.as_view(),
        name="delete-saved-filter",
    ),
    path(
        "active-hnv-view-type/",
        views.ActiveView.as_view(),
        name="active-hnv-view-type",
    ),
    path(
        "search-in-instance-ids/",
        views.SearchInIds.as_view(),
        name="search-in-instance-ids",
    ),
    path(
        "last-applied-filter/",
        views.LastAppliedFilter.as_view(),
        name="last-applied-filter",
    ),
    path(
        "generic-delete/",
        views.HorillaDeleteConfirmationView.as_view(),
        name="generic-delete",
    ),
    path(
        "horilla-history-revert/<int:pk>/<int:history_id>/",
        history.HorillaHistoryView.as_view(),
        name="history-revert",
    ),
    path(
        "generic-history/<int:pk>/",
        history.HorillaHistoryView.as_view(),
        name="generic-history",
    ),
    path(
        "dynamic-path/<str:field>/<str:session_key>/",
        views.DynamicView.as_view(),
        name="dynamic-path",
    ),
    path("export-list-view/<slug:short_id>/", views.export_data, name="export-list"),
    path(
        "hzp-tab/<str:tab_key>/<int:pk>/",
        dispatch_profile_tab,
        name="hzp-profile-tab",
    ),
]

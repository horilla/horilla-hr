"""
urls.py

SCIM endpoints accept paths with or without a trailing slash: IdPs build
URLs as "<base>/Users" and do not follow redirects on POST/PATCH.
"""

from django.urls import path, re_path

from horilla_scim import api, views

urlpatterns = [
    path("settings/scim-settings/", views.scim_settings_view, name="scim-settings"),
    path(
        "settings/scim-settings/tokens/",
        views.scim_token_create,
        name="scim-token-create",
    ),
    path(
        "settings/scim-settings/tokens/<int:token_id>/revoke/",
        views.scim_token_revoke,
        name="scim-token-revoke",
    ),
    re_path(
        r"^scim/v2/ServiceProviderConfig/?$",
        api.ServiceProviderConfigView.as_view(),
        name="scim-service-provider-config",
    ),
    re_path(
        r"^scim/v2/ResourceTypes/?$",
        api.ResourceTypesView.as_view(),
        name="scim-resource-types",
    ),
    re_path(
        r"^scim/v2/ResourceTypes/(?P<name>[^/]+)/?$",
        api.ResourceTypesView.as_view(),
        name="scim-resource-type",
    ),
    re_path(r"^scim/v2/Schemas/?$", api.SchemasView.as_view(), name="scim-schemas"),
    re_path(
        r"^scim/v2/Schemas/(?P<urn>[^/]+)/?$",
        api.SchemasView.as_view(),
        name="scim-schema",
    ),
    re_path(r"^scim/v2/Users/?$", api.UsersView.as_view(), name="scim-users"),
    re_path(
        r"^scim/v2/Users/(?P<scim_id>[^/]+)/?$",
        api.UserDetailView.as_view(),
        name="scim-user-detail",
    ),
]

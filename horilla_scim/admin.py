"""
Read-only, superuser-only views of the SCIM models. Configuration and tokens
are managed on the SCIM settings page; like that page, the admin must not be
reachable through a delegable model permission.
"""

from django.contrib import admin

from .models import ScimProvider, ScimToken


class ReadOnlySuperuserAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScimProvider)
class ScimProviderAdmin(ReadOnlySuperuserAdmin):
    list_display = ("name", "company", "is_enabled", "delete_mode")


@admin.register(ScimToken)
class ScimTokenAdmin(ReadOnlySuperuserAdmin):
    list_display = ("provider", "created_at")
    readonly_fields = ("token_hash", "created_at")

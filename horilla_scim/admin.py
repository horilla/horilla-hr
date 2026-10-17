from django.contrib import admin

from .models import ScimProvider, ScimToken


@admin.register(ScimProvider)
class ScimProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_enabled", "delete_mode")


@admin.register(ScimToken)
class ScimTokenAdmin(admin.ModelAdmin):
    list_display = ("prefix", "provider", "created_at", "last_used_at", "revoked_at")
    readonly_fields = ("token_hash", "prefix", "created_at", "last_used_at")

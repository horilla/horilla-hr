"""Django admin registration for the tour engine (support/debugging)."""

from django.contrib import admin

from horilla_tour.models import (
    Tour,
    TourProgress,
    TourStep,
    TourStepTranslation,
    TourTranslation,
)


class TourStepInline(admin.TabularInline):
    model = TourStep
    extra = 0
    ordering = ("sequence",)


class TourTranslationInline(admin.TabularInline):
    model = TourTranslation
    extra = 0
    readonly_fields = ("language", "title", "description")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class TourStepTranslationInline(admin.TabularInline):
    model = TourStepTranslation
    extra = 0
    readonly_fields = ("language", "title", "description")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "audience",
        "trigger",
        "is_published",
        "company_id",
    )
    list_filter = ("audience", "trigger", "is_published", "match_type")
    search_fields = ("title", "slug", "page_match")
    inlines = [TourStepInline, TourTranslationInline]


@admin.register(TourStep)
class TourStepAdmin(admin.ModelAdmin):
    list_display = ("title", "tour", "sequence")
    list_filter = ("tour",)
    search_fields = ("title", "tour__title")
    inlines = [TourStepTranslationInline]


@admin.register(TourProgress)
class TourProgressAdmin(admin.ModelAdmin):
    list_display = ("tour", "user", "status", "last_step", "completed_at")
    list_filter = ("status",)
    search_fields = ("tour__title", "user__username")

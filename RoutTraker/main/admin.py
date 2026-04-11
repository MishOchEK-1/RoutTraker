from django.contrib import admin

from .models import (
    ActivityLog,
    Cabinet,
    CabinetCheck,
    InspectionState,
)


@admin.register(Cabinet)
class CabinetAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "included", "can_be_skipped")
    list_editable = ("sort_order", "included", "can_be_skipped")
    search_fields = ("name",)
    ordering = ("sort_order", "name")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "cabinet_name", "item_title", "user")
    list_filter = ("action",)
    search_fields = ("cabinet_name", "item_title", "details", "user__username")
    autocomplete_fields = ("user",)


@admin.register(CabinetCheck)
class CabinetCheckAdmin(admin.ModelAdmin):
    list_display = ("cabinet", "status", "updated_by", "updated_at")
    list_filter = ("status",)
    search_fields = ("cabinet__name", "comment", "updated_by__username")
    autocomplete_fields = ("cabinet", "updated_by")


@admin.register(InspectionState)
class InspectionStateAdmin(admin.ModelAdmin):
    list_display = ("round_number", "last_reset_by", "last_reset_at")
    autocomplete_fields = ("last_reset_by",)

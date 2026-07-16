from django.contrib import admin

from .models import RenderSchedule


@admin.register(RenderSchedule)
class RenderScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "render", "is_enabled", "cron_expression", "interval_seconds", "next_run_at")
    list_filter = ("is_enabled",)
    search_fields = ("name", "render__display_name", "render__bluemap_map_id")
    autocomplete_fields = ("render", "created_by")

# Register your models here.

from django.contrib import admin

from .models import RenderArtifact, RenderJob, RenderLogChunk


class RenderLogChunkInline(admin.TabularInline):
    model = RenderLogChunk
    extra = 0
    readonly_fields = ("created_at",)


class RenderArtifactInline(admin.TabularInline):
    model = RenderArtifact
    extra = 0


@admin.register(RenderJob)
class RenderJobAdmin(admin.ModelAdmin):
    list_display = (
        "render",
        "operation",
        "status",
        "progress",
        "exit_code",
        "created_at",
        "finished_at",
    )
    list_filter = ("operation", "status")
    search_fields = ("render__display_name", "render__bluemap_map_id")
    autocomplete_fields = ("render", "requested_by")
    inlines = (RenderLogChunkInline, RenderArtifactInline)

# Register your models here.

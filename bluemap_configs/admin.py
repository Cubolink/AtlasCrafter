from django.contrib import admin

from .models import BlueMapProfile, BlueMapRenderConfig, ConfigRevision, GeneratedConfigFile


@admin.register(BlueMapProfile)
class BlueMapProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


class ConfigRevisionInline(admin.TabularInline):
    model = ConfigRevision
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(BlueMapRenderConfig)
class BlueMapRenderConfigAdmin(admin.ModelAdmin):
    list_display = ("render", "profile", "last_generated_at", "adopted_manual_file")
    list_filter = ("profile", "adopted_manual_file")
    search_fields = ("render__display_name", "render__bluemap_map_id")
    autocomplete_fields = ("render", "profile")
    inlines = (ConfigRevisionInline,)


@admin.register(GeneratedConfigFile)
class GeneratedConfigFileAdmin(admin.ModelAdmin):
    list_display = ("path", "render_config", "last_written_at")
    search_fields = ("path", "render_config__render__display_name")
    autocomplete_fields = ("render_config",)

# Register your models here.

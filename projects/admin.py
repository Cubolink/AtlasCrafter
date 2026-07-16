from django.contrib import admin

from .models import Atlas, Project, ProjectVisibleWorld, Region, Render, WorldFolder

@admin.register(WorldFolder)
class WorldFolderAdmin(admin.ModelAdmin):
    list_display = ("display_name", "source_path", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("display_name", "source_path")


class ProjectVisibleWorldInline(admin.TabularInline):
    model = ProjectVisibleWorld
    extra = 0
    autocomplete_fields = ("world_folder", "made_visible_by")


class AtlasInline(admin.TabularInline):
    model = Atlas
    extra = 0
    autocomplete_fields = ("world_folder",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner_team", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug", "owner_team")
    inlines = (ProjectVisibleWorldInline, AtlasInline)


class RenderInline(admin.TabularInline):
    model = Render
    extra = 0
    fields = ("display_name", "bluemap_map_id", "dimension", "perspective_preset", "is_enabled")


@admin.register(Atlas)
class AtlasAdmin(admin.ModelAdmin):
    list_display = ("display_name", "project", "world_folder", "is_active", "updated_at")
    list_filter = ("project", "is_active")
    prepopulated_fields = {"slug": ("display_name",)}
    search_fields = ("display_name", "world_folder__display_name", "project__name")
    autocomplete_fields = ("project", "world_folder")
    inlines = (RenderInline,)


@admin.register(Render)
class RenderAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "atlas",
        "bluemap_map_id",
        "dimension",
        "perspective_preset",
        "is_enabled",
    )
    list_filter = ("dimension", "perspective_preset", "is_enabled")
    search_fields = ("display_name", "bluemap_map_id", "atlas__display_name", "atlas__project__name")
    autocomplete_fields = ("atlas", "region")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "min_x", "min_z", "max_x", "max_z", "min_y", "max_y")
    search_fields = ("name",)
# Register your models here.

from django.contrib import admin

from .models import ProjectMembership


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "role", "created_at")
    list_filter = ("role", "project")
    search_fields = ("user__username", "user__email", "project__name")
    autocomplete_fields = ("user", "project")

# Register your models here.

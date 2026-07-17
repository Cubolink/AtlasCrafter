from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from renders.models import RenderJob
from .forms import (
    AtlasCreateForm,
    AtlasEditForm,
    ProjectUserAddForm,
    RENDER_ADVANCED_FIELDS,
    RENDER_BASIC_FIELDS,
    RenderCreateForm,
    RenderEditForm,
    WorldFolderForm,
)
from .models import Atlas, Project, Render, WorldFolder
from .permissions import can_manage_project
from .world_discovery import build_world_tree, scan_source_worlds


def superuser_required(user):
    return user.is_authenticated and user.is_superuser


@login_required
def dashboard(request):
    if request.user.is_superuser:
        projects = Project.objects.prefetch_related("atlases__renders").all()
    else:
        project_ids = ProjectMembership.objects.filter(user=request.user).values_list(
            "project_id",
            flat=True,
        )
        projects = Project.objects.filter(id__in=project_ids).prefetch_related("atlases__renders")

    return render(request, "projects/dashboard.html", {"projects": projects})


@login_required
@user_passes_test(superuser_required)
def world_folders(request):
    worlds = WorldFolder.objects.all()
    return render(
        request,
        "projects/world_folders.html",
        {
            "source_root": settings.SOURCE_WORLDS_DIR,
            "tree": build_world_tree(worlds),
            "worlds": worlds,
        },
    )


@login_required
@user_passes_test(superuser_required)
@require_POST
def scan_world_folders(request):
    result = scan_source_worlds()
    messages.success(
        request,
        (
            f"Scan complete. Added {len(result.created)}, updated {len(result.updated)}, "
            f"already known {len(result.unchanged)}."
        ),
    )
    return redirect("world_folders")


@login_required
@user_passes_test(superuser_required)
def create_world_folder(request):
    form = WorldFolderForm()
    if request.method == "POST":
        form = WorldFolderForm(request.POST)
        if form.is_valid():
            world = form.save()
            messages.success(request, f"World folder '{world.display_name}' added.")
            return redirect("world_folders")

    return render(
        request,
        "projects/world_folder_form.html",
        {
            "form": form,
            "title": "Add World Folder",
            "submit_label": "Add World Folder",
        },
    )


@login_required
@user_passes_test(superuser_required)
def edit_world_folder(request, world_id: int):
    world = get_object_or_404(WorldFolder, id=world_id)
    form = WorldFolderForm(instance=world)
    if request.method == "POST":
        form = WorldFolderForm(request.POST, instance=world)
        if form.is_valid():
            world = form.save()
            messages.success(request, f"World folder '{world.display_name}' updated.")
            return redirect("world_folders")

    return render(
        request,
        "projects/world_folder_form.html",
        {
            "form": form,
            "world": world,
            "title": "Edit World Folder",
            "submit_label": "Save World Folder",
        },
    )


@login_required
def project_detail(request, slug: str):
    project = get_object_or_404(
        Project.objects.prefetch_related("atlases__renders", "visible_worlds"),
        slug=slug,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=project)

    can_manage = can_manage_project(request.user, project)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "can_manage_project": can_manage,
            "atlas_form": AtlasCreateForm(project=project) if can_manage else None,
            "project_user_add_form": ProjectUserAddForm(project=project) if can_manage else None,
            "memberships": project.memberships.select_related("user").all(),
            "atlas_sections": [
                {
                    "atlas": atlas,
                    "render_form": RenderCreateForm(atlas=atlas) if can_manage else None,
                }
                for atlas in project.atlases.all()
            ],
        },
    )


@login_required
@require_POST
def create_atlas(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to create Atlases.")

    form = AtlasCreateForm(request.POST, project=project)
    if form.is_valid():
        atlas = form.save()
        messages.success(request, f"Atlas '{atlas.display_name}' created.")
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def create_render(request, atlas_id: int):
    atlas = get_object_or_404(Atlas.objects.select_related("project"), id=atlas_id)
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to create Renders.")

    form = RenderCreateForm(request.POST, atlas=atlas)
    if form.is_valid():
        render = form.save()
        messages.success(request, f"Render '{render.display_name}' created.")
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect(atlas.project.get_absolute_url())


@login_required
def edit_render(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to edit this Render.")

    form = RenderEditForm(instance=render_obj)
    if request.method == "POST":
        form = RenderEditForm(request.POST, instance=render_obj)
        if form.is_valid():
            render_obj = form.save()
            messages.success(request, f"Render '{render_obj.display_name}' updated.")
            return redirect(render_obj.project.get_absolute_url())

    return render(
        request,
        "projects/render_form.html",
        {
            "render": render_obj,
            "form": form,
            "basic_fields": [form[field] for field in RENDER_BASIC_FIELDS],
            "advanced_fields": [form[field] for field in RENDER_ADVANCED_FIELDS],
            "title": "Edit Render",
            "submit_label": "Save Render",
        },
    )


@login_required
@require_POST
def delete_render(request, render_id: int):
    render_obj = get_object_or_404(Render.objects.select_related("atlas__project"), id=render_id)
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to delete this Render.")

    if render_has_active_jobs(render_obj):
        messages.error(request, "This Render has a queued or running job and cannot be deleted yet.")
        return redirect(render_obj.project.get_absolute_url())

    project = render_obj.project
    display_name = render_obj.display_name
    render_obj.delete()
    messages.success(request, f"Render '{display_name}' deleted.")
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def add_project_user(request, slug: str):
    project = get_object_or_404(Project, slug=slug)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to add Project users.")

    form = ProjectUserAddForm(request.POST, project=project)
    if form.is_valid():
        membership = form.save()
        messages.success(
            request,
            f"Added {membership.user.username} to this Project as Project User.",
        )
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect(project.get_absolute_url())


@login_required
def edit_atlas(request, atlas_id: int):
    atlas = get_object_or_404(Atlas.objects.select_related("project", "world_folder"), id=atlas_id)
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to edit this Atlas.")

    form = AtlasEditForm(instance=atlas)
    if request.method == "POST":
        form = AtlasEditForm(request.POST, instance=atlas)
        if form.is_valid():
            atlas = form.save()
            messages.success(request, f"Atlas '{atlas.display_name}' updated.")
            return redirect(atlas.project.get_absolute_url())

    return render(
        request,
        "projects/atlas_form.html",
        {
            "atlas": atlas,
            "form": form,
            "title": "Edit Atlas",
            "submit_label": "Save Atlas",
        },
    )


@login_required
@require_POST
def delete_atlas(request, atlas_id: int):
    atlas = get_object_or_404(Atlas.objects.select_related("project"), id=atlas_id)
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to delete this Atlas.")

    if atlas_has_active_jobs(atlas):
        messages.error(request, "This Atlas has queued or running render jobs and cannot be deleted yet.")
        return redirect(atlas.project.get_absolute_url())

    project = atlas.project
    display_name = atlas.display_name
    atlas.delete()
    messages.success(request, f"Atlas '{display_name}' deleted.")
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def remove_project_membership(request, slug: str, membership_id: int):
    project = get_object_or_404(Project, slug=slug)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to remove Project users.")

    membership = get_object_or_404(
        ProjectMembership.objects.select_related("user"),
        id=membership_id,
        project=project,
    )
    if not request.user.is_superuser and membership.role != ProjectMembership.Role.PROJECT_USER:
        raise PermissionDenied("Project Administrators can only remove Project Users.")

    username = membership.user.username
    membership.delete()
    messages.success(request, f"Removed {username} from this Project.")
    return redirect(project.get_absolute_url())


def render_has_active_jobs(render_obj: Render) -> bool:
    return render_obj.jobs.filter(
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).exists()


def atlas_has_active_jobs(atlas: Atlas) -> bool:
    return RenderJob.objects.filter(
        render__atlas=atlas,
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).exists()

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
    ProjectManageForm,
    ProjectUserAddForm,
    RENDER_ADVANCED_FIELDS,
    RENDER_BASIC_FIELDS,
    RenderCreateForm,
    RenderEditForm,
    WorldFolderForm,
)
from .models import Atlas, Project, Render, WorldFolder
from .permissions import can_manage_project
from .world_discovery import build_world_tree, scan_source_worlds, world_folder_exists


def superuser_required(user):
    return user.is_authenticated and user.is_superuser


def get_visible_project_or_404(request, slug: str, queryset=None):
    queryset = queryset or Project.objects.all()
    project = get_object_or_404(queryset, slug=slug)
    if not project.is_active and not request.user.is_superuser:
        raise PermissionDenied("This Project is archived.")
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=project)
    return project


def get_visible_atlas_or_404(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project", "world_folder"),
        id=atlas_id,
        is_active=True,
        project__is_active=True,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=atlas.project)
    return atlas


@login_required
def dashboard(request):
    if request.user.is_superuser:
        projects = Project.objects.filter(is_active=True).prefetch_related("atlases__renders")
    else:
        project_ids = ProjectMembership.objects.filter(user=request.user).values_list(
            "project_id",
            flat=True,
        )
        projects = Project.objects.filter(
            id__in=project_ids,
            is_active=True,
        ).prefetch_related("atlases__renders")

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
            f"restored {len(result.restored)}, archived missing {len(result.archived)}, "
            f"already known {len(result.unchanged)}."
        ),
    )
    return redirect("world_folders")


@login_required
@user_passes_test(superuser_required)
def manage_projects(request):
    projects = Project.objects.prefetch_related("visible_worlds").all()
    return render(
        request,
        "projects/manage_projects.html",
        {
            "projects": projects,
        },
    )


@login_required
@user_passes_test(superuser_required)
def create_project(request):
    form = ProjectManageForm()
    worlds = WorldFolder.objects.filter(is_active=True).order_by("display_name")
    if request.method == "POST":
        form = ProjectManageForm(request.POST)
        if form.is_valid():
            project = form.save()
            messages.success(request, f"Project '{project.name}' created.")
            return redirect("edit_project", project_id=project.id)

    return render_project_form(request, form, worlds, "Create Project", "Create Project")


@login_required
@user_passes_test(superuser_required)
def edit_project(request, project_id: int):
    project = get_object_or_404(Project, id=project_id)
    form = ProjectManageForm(instance=project)
    worlds = WorldFolder.objects.filter(is_active=True).order_by("display_name")
    if request.method == "POST":
        form = ProjectManageForm(request.POST, instance=project)
        if form.is_valid():
            project = form.save()
            messages.success(request, f"Project '{project.name}' updated.")
            return redirect("manage_projects")

    return render_project_form(request, form, worlds, "Edit Project", "Save Project", project)


@login_required
@user_passes_test(superuser_required)
@require_POST
def archive_project(request, project_id: int):
    project = get_object_or_404(Project, id=project_id)
    if project_has_active_jobs(project):
        messages.error(request, "This Project has queued or running render jobs and cannot be archived yet.")
        return redirect("manage_projects")

    project.is_active = False
    project.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"Project '{project.name}' archived.")
    return redirect("manage_projects")


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


def render_project_form(request, form, worlds, title, submit_label, project=None):
    return render(
        request,
        "projects/project_form.html",
        {
            "form": form,
            "project": project,
            "tree": build_world_tree(worlds),
            "worlds": worlds,
            "title": title,
            "submit_label": submit_label,
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
@user_passes_test(superuser_required)
@require_POST
def archive_world_folder(request, world_id: int):
    world = get_object_or_404(WorldFolder, id=world_id, is_active=True)
    world.is_active = False
    world.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"World folder '{world.display_name}' archived.")
    return redirect("world_folders")


@login_required
@user_passes_test(superuser_required)
@require_POST
def restore_world_folder(request, world_id: int):
    world = get_object_or_404(WorldFolder, id=world_id, is_active=False)
    if not world_folder_exists(world):
        messages.error(
            request,
            f"World folder '{world.display_name}' cannot be restored because level.dat was not found.",
        )
        return redirect("world_folders")

    world.is_active = True
    world.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"World folder '{world.display_name}' restored.")
    return redirect("world_folders")


@login_required
def project_detail(request, slug: str):
    project = get_visible_project_or_404(
        request,
        slug,
        Project.objects.prefetch_related("atlases__renders", "visible_worlds"),
    )

    can_manage = can_manage_project(request.user, project)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "can_manage_project": can_manage,
            "atlas_form": AtlasCreateForm(project=project) if can_manage else None,
            "archived_atlas_count": (
                project.atlases.filter(is_active=False).count() if can_manage else 0
            ),
            "atlas_sections": [
                {
                    "atlas": atlas,
                    "renders": atlas.renders.filter(is_enabled=True),
                    "archived_render_count": atlas.renders.filter(is_enabled=False).count(),
                }
                for atlas in project.atlases.filter(is_active=True)
            ],
        },
    )


@login_required
def project_members(request, slug: str):
    project = get_visible_project_or_404(request, slug)
    can_manage = can_manage_project(request.user, project)

    return render(
        request,
        "projects/project_members.html",
        {
            "project": project,
            "can_manage_project": can_manage,
            "project_user_add_form": ProjectUserAddForm(project=project) if can_manage else None,
            "memberships": project.memberships.select_related("user").all(),
        },
    )


@login_required
def project_worlds(request, slug: str):
    project = get_visible_project_or_404(
        request,
        slug,
        Project.objects.prefetch_related("visible_worlds"),
    )
    can_manage = can_manage_project(request.user, project)
    if can_manage:
        world_folders = project.visible_worlds.all()
        worlds_title = "Visible World Folders"
        empty_message = "No world folders are visible to this Project."
    else:
        world_folders = WorldFolder.objects.filter(
            atlases__project=project,
            atlases__is_active=True,
        ).distinct().order_by("display_name")
        worlds_title = "Atlas World Folders"
        empty_message = "No world folders are in use by this Project's Atlases yet."

    return render(
        request,
        "projects/project_worlds.html",
        {
            "project": project,
            "can_manage_project": can_manage,
            "world_folders": world_folders,
            "worlds_title": worlds_title,
            "empty_message": empty_message,
        },
    )


@login_required
def atlas_detail(request, atlas_id: int):
    atlas = get_visible_atlas_or_404(request, atlas_id)
    can_manage = can_manage_project(request.user, atlas.project)
    return render(
        request,
        "projects/atlas_detail.html",
        {
            "atlas": atlas,
            "project": atlas.project,
            "can_manage_project": can_manage,
            "renders": atlas.renders.filter(is_enabled=True),
            "archived_render_count": atlas.renders.filter(is_enabled=False).count() if can_manage else 0,
            "render_form": RenderCreateForm(atlas=atlas) if can_manage else None,
        },
    )


@login_required
def archived_atlases(request, slug: str):
    project = get_object_or_404(Project, slug=slug, is_active=True)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to view archived Atlases.")

    atlases = project.atlases.filter(is_active=False).select_related("world_folder")
    return render(
        request,
        "projects/archived_atlases.html",
        {
            "project": project,
            "atlases": atlases,
        },
    )


@login_required
def archived_renders(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project", "world_folder"),
        id=atlas_id,
        is_active=True,
        project__is_active=True,
    )
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to view archived Renders.")

    renders = atlas.renders.filter(is_enabled=False)
    return render(
        request,
        "projects/archived_renders.html",
        {
            "atlas": atlas,
            "project": atlas.project,
            "renders": renders,
        },
    )


@login_required
@require_POST
def create_atlas(request, slug: str):
    project = get_object_or_404(Project, slug=slug, is_active=True)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to create Atlases.")

    form = AtlasCreateForm(request.POST, project=project)
    if form.is_valid():
        atlas = form.save()
        messages.success(request, f"Atlas '{atlas.display_name}' created.")
        return redirect("atlas_detail", atlas_id=atlas.id)
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def create_render(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project"),
        id=atlas_id,
        is_active=True,
        project__is_active=True,
    )
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to create Renders.")

    form = RenderCreateForm(request.POST, atlas=atlas)
    if form.is_valid():
        render = form.save()
        messages.success(request, f"Render '{render.display_name}' created.")
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect("atlas_detail", atlas_id=atlas.id)


@login_required
def edit_render(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to edit this Render.")

    form = RenderEditForm(instance=render_obj)
    if request.method == "POST":
        form = RenderEditForm(request.POST, instance=render_obj)
        if form.is_valid():
            render_obj = form.save()
            messages.success(request, f"Render '{render_obj.display_name}' updated.")
            return redirect("atlas_detail", atlas_id=render_obj.atlas_id)

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
def archive_render(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project"),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to archive this Render.")

    if render_has_active_jobs(render_obj):
        messages.error(request, "This Render has a queued or running job and cannot be archived yet.")
        return redirect("atlas_detail", atlas_id=render_obj.atlas_id)

    display_name = render_obj.display_name
    render_obj.is_enabled = False
    render_obj.save(update_fields=["is_enabled", "updated_at"])
    messages.success(request, f"Render '{display_name}' archived.")
    return redirect("atlas_detail", atlas_id=render_obj.atlas_id)


@login_required
@require_POST
def restore_render(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project"),
        id=render_id,
        is_enabled=False,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to restore this Render.")

    render_obj.is_enabled = True
    render_obj.save(update_fields=["is_enabled", "updated_at"])
    messages.success(request, f"Render '{render_obj.display_name}' restored.")
    return redirect("archived_renders", atlas_id=render_obj.atlas_id)


@login_required
@require_POST
def add_project_user(request, slug: str):
    project = get_object_or_404(Project, slug=slug, is_active=True)
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
    return redirect("project_members", slug=project.slug)


@login_required
def edit_atlas(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project", "world_folder"),
        id=atlas_id,
        is_active=True,
        project__is_active=True,
    )
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to edit this Atlas.")

    form = AtlasEditForm(instance=atlas)
    if request.method == "POST":
        form = AtlasEditForm(request.POST, instance=atlas)
        if form.is_valid():
            atlas = form.save()
            messages.success(request, f"Atlas '{atlas.display_name}' updated.")
            return redirect("atlas_detail", atlas_id=atlas.id)

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
def archive_atlas(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project"),
        id=atlas_id,
        is_active=True,
        project__is_active=True,
    )
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to archive this Atlas.")

    if atlas_has_active_jobs(atlas):
        messages.error(request, "This Atlas has queued or running render jobs and cannot be archived yet.")
        return redirect("atlas_detail", atlas_id=atlas.id)

    project = atlas.project
    display_name = atlas.display_name
    atlas.is_active = False
    atlas.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"Atlas '{display_name}' archived.")
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def restore_atlas(request, atlas_id: int):
    atlas = get_object_or_404(
        Atlas.objects.select_related("project"),
        id=atlas_id,
        is_active=False,
        project__is_active=True,
    )
    if not can_manage_project(request.user, atlas.project):
        raise PermissionDenied("You do not have permission to restore this Atlas.")

    atlas.is_active = True
    atlas.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"Atlas '{atlas.display_name}' restored.")
    return redirect("archived_atlases", slug=atlas.project.slug)


@login_required
@require_POST
def remove_project_membership(request, slug: str, membership_id: int):
    project = get_object_or_404(Project, slug=slug, is_active=True)
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
    return redirect("project_members", slug=project.slug)


def render_has_active_jobs(render_obj: Render) -> bool:
    return render_obj.jobs.filter(
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).exists()


def atlas_has_active_jobs(atlas: Atlas) -> bool:
    return RenderJob.objects.filter(
        render__atlas=atlas,
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).exists()


def project_has_active_jobs(project: Project) -> bool:
    return RenderJob.objects.filter(
        render__atlas__project=project,
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).exists()

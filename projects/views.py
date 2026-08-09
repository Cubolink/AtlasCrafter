from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from renders.models import RenderJob
from renders.services import (
    RenderConfigurationError,
    enqueue_render,
    has_active_render_job,
    preview_render_config,
    resolve_render_resources,
)
from viewer.views import render_output_exists
from .forms import (
    AtlasCreateForm,
    AtlasEditForm,
    MarkerSetForm,
    POIMarkerForm,
    ProjectManageForm,
    ProjectUserAddForm,
    RENDER_ADVANCED_FIELDS,
    RENDER_BASIC_FIELDS,
    RENDER_RESOURCE_FIELDS,
    RENDER_PRESET_DEFAULTS,
    RENDER_PRESET_SUMMARIES,
    RenderCreateForm,
    RenderEditForm,
    MinecraftResourceSourceForm,
    WorldFolderForm,
)
from .models import (
    Atlas,
    Marker,
    MarkerSet,
    MinecraftResourceSource,
    MinecraftServer,
    Project,
    Render,
    WorldFolder,
)
from .markers import build_marker_management_state
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
    worlds = WorldFolder.objects.select_related(
        "minecraft_server",
        "default_resource_source",
    ).all()
    resource_sources = list(MinecraftResourceSource.objects.all())
    tree = build_world_tree(worlds, resource_sources=resource_sources)
    resource_tree = build_world_tree(
        [],
        settings.BLUEMAP_RESOURCE_SOURCES_DIR,
        resource_sources=resource_sources,
    )
    return render(
        request,
        "projects/world_folders.html",
        {
            "source_root": settings.SOURCE_WORLDS_DIR,
            "tree": tree,
            "has_tree": bool(tree["worlds"] or tree["children"] or tree["resource_sources"]),
            "resource_tree": resource_tree,
            "has_resource_tree": bool(
                resource_tree["children"] or resource_tree["resource_sources"]
            ),
            "worlds": worlds,
            "servers": MinecraftServer.objects.select_related("resource_source").all(),
            "resource_sources": resource_sources,
            "resource_sources_root": settings.BLUEMAP_RESOURCE_SOURCES_DIR,
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
            f"already known {len(result.unchanged)}. Detected {len(result.servers)} server(s) "
            f"and {len(result.resource_sources)} resource source(s)."
        ),
    )
    return redirect("world_folders")


@login_required
@user_passes_test(superuser_required)
def create_resource_source(request):
    form = MinecraftResourceSourceForm()
    if request.method == "POST":
        form = MinecraftResourceSourceForm(request.POST)
        if form.is_valid():
            source = form.save()
            messages.success(request, f"Resource source '{source.display_name}' added.")
            return redirect("world_folders")
    return render_resource_source_form(request, form, "Add Resource Source", "Add Source")


@login_required
@user_passes_test(superuser_required)
def edit_resource_source(request, source_id: int):
    source = get_object_or_404(MinecraftResourceSource, id=source_id)
    form = MinecraftResourceSourceForm(instance=source)
    if request.method == "POST":
        form = MinecraftResourceSourceForm(request.POST, instance=source)
        if form.is_valid():
            source = form.save()
            messages.success(request, f"Resource source '{source.display_name}' updated.")
            return redirect("world_folders")
    return render_resource_source_form(
        request,
        form,
        "Edit Resource Source",
        "Save Source",
        source,
    )


def render_resource_source_form(request, form, title, submit_label, source=None):
    return render(
        request,
        "projects/resource_source_form.html",
        {
            "form": form,
            "source": source,
            "title": title,
            "submit_label": submit_label,
            "source_root": settings.SOURCE_WORLDS_DIR,
            "resource_sources_root": settings.BLUEMAP_RESOURCE_SOURCES_DIR,
        },
    )


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
    renders = atlas.renders.filter(is_enabled=True).prefetch_related("jobs")
    return render(
        request,
        "projects/atlas_detail.html",
        {
            "atlas": atlas,
            "project": atlas.project,
            "can_manage_project": can_manage,
            "render_sections": [
                {
                    "render": render,
                    "latest_job": render.jobs.first(),
                }
                for render in renders
            ],
            "archived_render_count": atlas.renders.filter(is_enabled=False).count() if can_manage else 0,
            "render_form": RenderCreateForm(atlas=atlas) if can_manage else None,
            "render_preset_summaries": RENDER_PRESET_SUMMARIES,
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
        Render.objects.select_related(
            "atlas__project",
            "atlas__world_folder__minecraft_server__resource_source",
            "atlas__world_folder__default_resource_source",
            "resource_source",
        ),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to edit this Render.")

    allow_custom_paths = request.user.is_superuser
    form = RenderEditForm(instance=render_obj, allow_custom_paths=allow_custom_paths)
    if request.method == "POST":
        form = RenderEditForm(
            request.POST,
            instance=render_obj,
            allow_custom_paths=allow_custom_paths,
        )
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
            "resource_fields": [form[field] for field in RENDER_RESOURCE_FIELDS],
            "advanced_fields": [form[field] for field in RENDER_ADVANCED_FIELDS],
            "effective_resource_summary": effective_resource_summary(render_obj),
            "allow_custom_resource_paths": allow_custom_paths,
            "config_content": preview_render_config(render_obj)[1],
            "render_preset_defaults": RENDER_PRESET_DEFAULTS,
            "render_preset_summaries": RENDER_PRESET_SUMMARIES,
            "title": "Edit Render",
            "submit_label": "Save Render",
        },
    )


def get_manageable_render_or_404(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to manage markers for this Render.")
    return render_obj


def get_manageable_marker_set_or_404(request, marker_set_id: int):
    marker_set = get_object_or_404(
        MarkerSet.objects.select_related(
            "render__atlas__project",
            "render__atlas__world_folder",
        ),
        id=marker_set_id,
        render__is_enabled=True,
        render__atlas__is_active=True,
        render__atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, marker_set.render.project):
        raise PermissionDenied("You do not have permission to manage this marker set.")
    return marker_set


@login_required
def render_markers(request, render_id: int):
    render_obj = get_manageable_render_or_404(request, render_id)
    marker_editor = build_marker_editor(request, render_obj)
    marker_form = marker_editor["form"]
    async_request = is_marker_workspace_request(request)

    if request.method == "POST":
        if marker_form is None:
            if async_request:
                return JsonResponse({"error": "Invalid marker editor action."}, status=400)
        elif marker_form.is_valid():
            marker = marker_form.save(commit=False)
            if marker_editor["mode"] == "create":
                marker.marker_set = marker_editor["marker_set"]
                marker.marker_type = Marker.Type.POI
                success_message = f"Marker '{marker.label}' created."
            else:
                success_message = f"Marker '{marker.label}' updated."
            marker.save()
            marker_editor = marker_editor_for_marker(marker)
            if async_request:
                return marker_workspace_response(
                    request,
                    render_obj,
                    marker_editor,
                    notice={
                        "level": "success",
                        "message": success_message,
                        "presentation": "inline-save",
                    },
                )
            messages.success(request, success_message)
            manager_url = reverse("render_markers", kwargs={"render_id": render_obj.id})
            return redirect(f"{manager_url}?edit={marker.id}#marker-editor")
        elif async_request:
            return marker_workspace_response(
                request,
                render_obj,
                marker_editor,
                notice={
                    "level": "error",
                    "message": "Review the highlighted marker fields.",
                },
                status=422,
            )

    if async_request:
        return marker_workspace_response(request, render_obj, marker_editor)
    context = marker_workspace_context(render_obj, marker_editor)
    return render(
        request,
        "projects/markers/marker_sets.html",
        {
            **context,
            "render_output_exists": render_output_exists(render_obj),
        },
    )


def marker_workspace_context(render_obj, marker_editor) -> dict:
    return {
        "render": render_obj,
        "marker_state": build_marker_management_state(render_obj),
        "active_job": render_obj.jobs.filter(
            status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING]
        ).first(),
        "latest_marker_job": render_obj.jobs.filter(
            operation=RenderJob.Operation.MARKERS
        ).first(),
        "marker_editor": marker_editor,
    }


def marker_workspace_response(
    request,
    render_obj,
    marker_editor,
    *,
    notice=None,
    status=200,
):
    context = marker_workspace_context(render_obj, marker_editor)
    active_job = context["active_job"]
    payload = {
        "marker_browser_html": render_to_string(
            "projects/markers/marker_browser.html",
            context,
            request=request,
        ),
        "marker_editor_html": render_to_string(
            "projects/markers/marker_editor_panel.html",
            context,
            request=request,
        ),
        "publication_status_html": render_to_string(
            "projects/markers/publication_status.html",
            context,
            request=request,
        ),
        "publish_action_html": render_to_string(
            "projects/markers/publish_action.html",
            context,
            request=request,
        ),
        "active_job_id": active_job.id if active_job else None,
        "editor_url": marker_editor_url(render_obj, marker_editor),
        "notice": notice,
    }
    return JsonResponse(payload, status=status)


def marker_editor_for_marker(marker) -> dict:
    return {
        "mode": "edit",
        "marker_set": marker.marker_set,
        "marker": marker,
        "form": POIMarkerForm(instance=marker),
    }


def empty_marker_editor() -> dict:
    return {"mode": None, "marker_set": None, "marker": None, "form": None}


def marker_editor_url(render_obj, marker_editor) -> str:
    manager_url = reverse("render_markers", kwargs={"render_id": render_obj.id})
    if marker_editor["mode"] == "edit":
        return f"{manager_url}?edit={marker_editor['marker'].id}#marker-editor"
    if marker_editor["mode"] == "create":
        return f"{manager_url}?create={marker_editor['marker_set'].id}#marker-editor"
    return manager_url


def is_marker_workspace_request(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def build_marker_editor(request, render_obj) -> dict:
    mode = None
    marker_set = None
    marker = None
    marker_form = None

    if request.method == "POST":
        mode = request.POST.get("editor_action")
        if mode == "create":
            marker_set = get_object_or_404(
                render_obj.marker_sets,
                id=positive_int(request.POST.get("marker_set_id")),
            )
            marker_form = POIMarkerForm(request.POST)
        elif mode == "edit":
            marker = get_object_or_404(
                Marker.objects.select_related("marker_set"),
                id=positive_int(request.POST.get("marker_id")),
                marker_set__render=render_obj,
            )
            marker_set = marker.marker_set
            marker_form = POIMarkerForm(request.POST, instance=marker)
    else:
        marker_id = positive_int(request.GET.get("edit"))
        marker_set_id = positive_int(request.GET.get("create"))
        if marker_id is not None:
            marker = get_object_or_404(
                Marker.objects.select_related("marker_set"),
                id=marker_id,
                marker_set__render=render_obj,
            )
            mode = "edit"
            marker_set = marker.marker_set
            marker_form = POIMarkerForm(instance=marker)
        elif marker_set_id is not None:
            marker_set = get_object_or_404(
                render_obj.marker_sets,
                id=marker_set_id,
            )
            mode = "create"
            marker_form = POIMarkerForm()

    return {
        "mode": mode,
        "marker_set": marker_set,
        "marker": marker,
        "form": marker_form,
    }


def positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def queue_marker_publication(request, render_obj, *, notify=True) -> dict:
    if has_active_render_job(render_obj):
        result = {
            "job": None,
            "level": "warning",
            "message": "This Render already has a queued or running job. Publish Markers was not queued.",
        }
        if notify:
            messages.warning(request, result["message"])
        return result
    try:
        job = enqueue_render(
            render_obj,
            requested_by=request.user,
            operation=RenderJob.Operation.MARKERS,
        )
    except RenderConfigurationError as exc:
        result = {"job": None, "level": "error", "message": str(exc)}
        if notify:
            messages.error(request, result["message"])
        return result
    result = {
        "job": job,
        "level": "success",
        "message": f"Marker publishing job #{job.id} queued.",
    }
    if notify:
        messages.success(request, result["message"])
    return result


@login_required
def create_marker_set(request, render_id: int):
    render_obj = get_manageable_render_or_404(request, render_id)
    form = MarkerSetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        marker_set = form.save(commit=False)
        marker_set.render = render_obj
        marker_set.save()
        messages.success(request, f"Marker set '{marker_set.label}' created.")
        return redirect("render_markers", render_id=render_obj.id)
    return render(
        request,
        "projects/markers/marker_set_form.html",
        {
            "render": render_obj,
            "form": form,
            "title": "Create Marker Set",
            "submit_label": "Create Marker Set",
        },
    )


@login_required
def edit_marker_set(request, marker_set_id: int):
    marker_set = get_manageable_marker_set_or_404(request, marker_set_id)
    form = MarkerSetForm(request.POST or None, instance=marker_set)
    if request.method == "POST" and form.is_valid():
        marker_set = form.save()
        messages.success(request, f"Marker set '{marker_set.label}' updated.")
        return redirect("render_markers", render_id=marker_set.render_id)
    return render(
        request,
        "projects/markers/marker_set_form.html",
        {
            "render": marker_set.render,
            "marker_set": marker_set,
            "form": form,
            "title": "Edit Marker Set",
            "submit_label": "Save Marker Set",
        },
    )


@login_required
@require_POST
def delete_marker_set(request, marker_set_id: int):
    marker_set = get_manageable_marker_set_or_404(request, marker_set_id)
    render_obj = marker_set.render
    render_id = marker_set.render_id
    label = marker_set.label
    marker_set.delete()
    if is_marker_workspace_request(request):
        return marker_workspace_response(
            request,
            render_obj,
            empty_marker_editor(),
            notice={
                "level": "success",
                "message": f"Marker set '{label}' deleted.",
            },
        )
    messages.success(request, f"Marker set '{label}' deleted.")
    return redirect("render_markers", render_id=render_id)


@login_required
def create_marker(request, marker_set_id: int):
    marker_set = get_manageable_marker_set_or_404(request, marker_set_id)
    form = POIMarkerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        marker = form.save(commit=False)
        marker.marker_set = marker_set
        marker.marker_type = Marker.Type.POI
        marker.save()
        messages.success(request, f"Marker '{marker.label}' created.")
        return redirect("render_markers", render_id=marker_set.render_id)
    return render(
        request,
        "projects/markers/marker_form.html",
        {
            "render": marker_set.render,
            "marker_set": marker_set,
            "form": form,
            "title": "Create Point of Interest",
            "submit_label": "Create Marker",
        },
    )


@login_required
def edit_marker(request, marker_id: int):
    marker = get_object_or_404(
        Marker.objects.select_related(
            "marker_set__render__atlas__project",
            "marker_set__render__atlas__world_folder",
        ),
        id=marker_id,
        marker_set__render__is_enabled=True,
        marker_set__render__atlas__is_active=True,
        marker_set__render__atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, marker.render.project):
        raise PermissionDenied("You do not have permission to manage this marker.")
    form = POIMarkerForm(request.POST or None, instance=marker)
    if request.method == "POST" and form.is_valid():
        marker = form.save()
        messages.success(request, f"Marker '{marker.label}' updated.")
        return redirect("render_markers", render_id=marker.render.id)
    return render(
        request,
        "projects/markers/marker_form.html",
        {
            "render": marker.render,
            "marker_set": marker.marker_set,
            "marker": marker,
            "form": form,
            "title": "Edit Point of Interest",
            "submit_label": "Save Marker",
        },
    )


@login_required
@require_POST
def delete_marker(request, marker_id: int):
    marker = get_object_or_404(
        Marker.objects.select_related("marker_set__render__atlas__project"),
        id=marker_id,
        marker_set__render__is_enabled=True,
        marker_set__render__atlas__is_active=True,
        marker_set__render__atlas__project__is_active=True,
    )
    if not can_manage_project(request.user, marker.render.project):
        raise PermissionDenied("You do not have permission to delete this marker.")
    render_obj = marker.render
    render_id = render_obj.id
    label = marker.label
    marker.delete()
    if is_marker_workspace_request(request):
        return marker_workspace_response(
            request,
            render_obj,
            empty_marker_editor(),
            notice={"level": "success", "message": f"Marker '{label}' deleted."},
        )
    messages.success(request, f"Marker '{label}' deleted.")
    return redirect("render_markers", render_id=render_id)


@login_required
@require_POST
def publish_render_markers(request, render_id: int):
    render_obj = get_manageable_render_or_404(request, render_id)
    async_request = is_marker_workspace_request(request)
    publication = queue_marker_publication(
        request,
        render_obj,
        notify=not async_request,
    )
    if async_request:
        return marker_workspace_response(
            request,
            render_obj,
            empty_marker_editor(),
            notice={
                "level": publication["level"],
                "message": publication["message"],
            },
        )
    return redirect("render_markers", render_id=render_obj.id)


def effective_resource_summary(render_obj: Render) -> str:
    mods_path, minecraft_version = resolve_render_resources(render_obj)
    version_label = f"Minecraft {minecraft_version}" if minecraft_version else "Automatic Minecraft version"
    if mods_path:
        mod_count = len(list(mods_path.glob("*.jar")))
        return f"{version_label}; loading {mod_count} mod file(s) from {mods_path}."
    return f"{version_label}; mod resources disabled or unavailable."


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

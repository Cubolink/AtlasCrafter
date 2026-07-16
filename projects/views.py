from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from .forms import AtlasCreateForm, ProjectUserAddForm, RenderCreateForm
from .models import Atlas, Project
from .permissions import can_manage_project


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

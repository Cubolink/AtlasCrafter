from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from projects.models import Render
from renders.services import run_render, user_can_trigger_render


@login_required
def render_viewer(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=render_obj.project)

    jobs = render_obj.jobs.prefetch_related("log_chunks").all()[:10]
    viewer_entry_path = settings.BLUEMAP_WEBROOT_DIR / "index.html"
    return render(
        request,
        "viewer/render_viewer.html",
        {
            "render": render_obj,
            "jobs": jobs,
            "can_trigger_render": user_can_trigger_render(request.user, render_obj),
            "viewer_entry_exists": viewer_entry_path.is_file(),
        },
    )


@login_required
@require_POST
def trigger_render(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
    )
    if not user_can_trigger_render(request.user, render_obj):
        raise PermissionDenied("You do not have permission to trigger this Render.")

    job = run_render(render_obj, requested_by=request.user)
    if job.status == job.Status.SUCCEEDED:
        messages.success(request, "Render completed successfully.")
    else:
        messages.error(request, "Render failed. Check the job log below.")
    return redirect("render_viewer", render_id=render_obj.id)

# Create your views here.

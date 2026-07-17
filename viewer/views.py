from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from projects.models import Render
from renders.models import RenderJob
from renders.services import (
    cancel_queued_render_job,
    enqueue_render,
    has_active_render_job,
    user_can_trigger_render,
)


ACTIVE_JOB_STATUSES = [RenderJob.Status.QUEUED, RenderJob.Status.RUNNING]


def get_visible_render_or_404(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=render_obj.project)
    return render_obj


def get_visible_job_or_404(request, job_id: int):
    job = get_object_or_404(
        RenderJob.objects.select_related("render__atlas__project", "render__atlas__world_folder", "requested_by")
        .prefetch_related("log_chunks", "artifacts"),
        id=job_id,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=job.render.project)
    return job


@login_required
def render_viewer(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)

    jobs = render_obj.jobs.prefetch_related("log_chunks").all()[:10]
    active_job = render_obj.jobs.filter(status__in=ACTIVE_JOB_STATUSES).first()
    viewer_entry_path = settings.BLUEMAP_WEBROOT_DIR / "index.html"
    return render(
        request,
        "viewer/render_viewer.html",
        {
            "render": render_obj,
            "jobs": jobs,
            "can_trigger_render": user_can_trigger_render(request.user, render_obj),
            "active_job": active_job,
            "has_active_job": active_job is not None,
            "viewer_entry_exists": viewer_entry_path.is_file(),
        },
    )


@login_required
@require_POST
def trigger_render(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)
    if not user_can_trigger_render(request.user, render_obj):
        raise PermissionDenied("You do not have permission to trigger this Render.")

    if has_active_render_job(render_obj):
        messages.warning(request, "This Render already has a queued or running job.")
        return redirect("render_viewer", render_id=render_obj.id)

    job = enqueue_render(render_obj, requested_by=request.user)
    messages.success(request, f"Render job #{job.id} queued.")
    return redirect("render_viewer", render_id=render_obj.id)


@login_required
def render_job_detail(request, job_id: int):
    job = get_visible_job_or_404(request, job_id)
    return render(
        request,
        "viewer/render_job_detail.html",
        {
            "job": job,
            "render": job.render,
            "can_cancel_job": (
                job.status == RenderJob.Status.QUEUED
                and user_can_trigger_render(request.user, job.render)
            ),
        },
    )


@login_required
@require_POST
def cancel_render_job(request, job_id: int):
    job = get_visible_job_or_404(request, job_id)
    if not user_can_trigger_render(request.user, job.render):
        raise PermissionDenied("You do not have permission to cancel this Render job.")

    if cancel_queued_render_job(job, request.user):
        messages.success(request, f"Render job #{job.id} canceled.")
    else:
        messages.warning(request, "Only queued render jobs can be canceled.")
    return redirect("render_job_detail", job_id=job.id)


@login_required
def render_status(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)
    active_job = render_obj.jobs.filter(status__in=ACTIVE_JOB_STATUSES).first()
    latest_job = render_obj.jobs.first()
    job = active_job or latest_job

    return JsonResponse(
        {
            "has_active_job": active_job is not None,
            "job": serialize_job(job),
        }
    )


def serialize_job(job):
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "status_label": job.get_status_display(),
        "updated_at": job.updated_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }

# Create your views here.

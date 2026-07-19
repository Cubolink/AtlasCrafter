from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import ProjectMembership
from projects.models import Render
from projects.permissions import can_manage_project
from renders.models import RenderJob
from renders.services import (
    cancel_queued_render_job,
    enqueue_render,
    has_active_render_job,
    preview_render_config,
    render_world_folder_is_available,
    user_can_trigger_render,
)


ACTIVE_JOB_STATUSES = [RenderJob.Status.QUEUED, RenderJob.Status.RUNNING]


def get_visible_render_or_404(request, render_id: int):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project", "atlas__world_folder"),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
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
    if not (request.user.is_superuser or request.user.is_staff):
        get_object_or_404(ProjectMembership, user=request.user, project=job.render.project)
    return job


@login_required
def render_viewer(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)

    jobs = render_obj.jobs.prefetch_related("log_chunks").all()[:10]
    active_job = render_obj.jobs.filter(status__in=ACTIVE_JOB_STATUSES).first()
    source_available = render_world_folder_is_available(render_obj)
    return render(
        request,
        "viewer/render_viewer.html",
        {
            "render": render_obj,
            "jobs": jobs,
            "can_manage_render": can_manage_project(request.user, render_obj.project),
            "can_trigger_render": user_can_trigger_render(request.user, render_obj),
            "source_available": source_available,
            "active_job": active_job,
            "has_active_job": active_job is not None,
            "render_output_exists": render_output_exists(render_obj),
        },
    )


@login_required
def render_config_preview(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)
    if not user_can_trigger_render(request.user, render_obj):
        raise PermissionDenied("You do not have permission to preview this Render config.")

    render_config, content = preview_render_config(render_obj)
    return render(
        request,
        "viewer/render_config_preview.html",
        {
            "render": render_obj,
            "render_config": render_config,
            "config_content": content,
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
    if job.status == RenderJob.Status.FAILED:
        messages.error(
            request,
            (
                f"Render job #{job.id} failed before queueing because the Minecraft "
                "world folder is archived or missing."
            ),
        )
    else:
        messages.success(request, f"Render job #{job.id} queued.")
    return redirect("render_viewer", render_id=render_obj.id)


@login_required
@require_POST
def rebuild_render(request, render_id: int):
    render_obj = get_visible_render_or_404(request, render_id)
    if not can_manage_project(request.user, render_obj.project):
        raise PermissionDenied("You do not have permission to rebuild this Render.")

    if has_active_render_job(render_obj):
        messages.warning(request, "This Render already has a queued or running job.")
        return redirect("render_viewer", render_id=render_obj.id)

    job = enqueue_render(
        render_obj,
        requested_by=request.user,
        operation=RenderJob.Operation.REBUILD,
    )
    if job.status == RenderJob.Status.FAILED:
        messages.error(
            request,
            (
                f"Rebuild job #{job.id} failed before queueing because the Minecraft "
                "world folder is archived or missing."
            ),
        )
    else:
        messages.success(request, f"Full rebuild job #{job.id} queued.")
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
        "operation": job.operation,
        "operation_label": job.get_operation_display(),
        "status": job.status,
        "status_label": job.get_status_display(),
        "updated_at": job.updated_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def render_output_exists(render_obj: Render) -> bool:
    if not (settings.BLUEMAP_WEBROOT_DIR / "index.html").is_file():
        return False
    return any(
        (settings.BLUEMAP_WEBROOT_DIR / "maps" / map_id / "settings.json").is_file()
        or (settings.BLUEMAP_WEBROOT_DIR / "maps" / map_id / "settings.json.gz").is_file()
        for map_id in viewer_map_ids(render_obj)
    )


def viewer_map_ids(render_obj: Render) -> set[str]:
    return {render_obj.bluemap_map_id, render_obj.bluemap_map_id.replace("-", "_")}

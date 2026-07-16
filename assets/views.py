from pathlib import PurePosixPath
import mimetypes

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404

from accounts.models import ProjectMembership
from projects.models import Render


@login_required
def protected_render_asset(request, render_id: int, asset_path: str):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project"),
        id=render_id,
        is_enabled=True,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=render_obj.project)

    safe_path = PurePosixPath(asset_path)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        raise Http404("Asset not found")

    asset_file = settings.BLUEMAP_WEBROOT_DIR / safe_path.as_posix()
    compressed_asset_file = asset_file.with_name(f"{asset_file.name}.gz")
    if settings.DEBUG:
        if not asset_file.is_file() and compressed_asset_file.is_file():
            asset_file = compressed_asset_file
        if not asset_file.is_file():
            raise Http404("Asset not found")
        response = FileResponse(
            asset_file.open("rb"),
            content_type=content_type_for_requested_path(safe_path, asset_file),
        )
        if asset_file.suffix == ".gz":
            response["Content-Encoding"] = "gzip"
        return response

    internal_root = settings.INTERNAL_ACCEL_ROOT.rstrip("/")
    response = HttpResponse()
    internal_path = safe_path.as_posix()
    if not asset_file.is_file() and compressed_asset_file.is_file():
        internal_path = f"{internal_path}.gz"
        response["Content-Encoding"] = "gzip"
    response["X-Accel-Redirect"] = f"{internal_root}/{internal_path}"
    return response


def content_type_for_requested_path(requested_path, actual_path):
    if actual_path.name.endswith(".json.gz") or requested_path.name.endswith(".json"):
        return "application/json"
    if requested_path.suffix == ".webmanifest":
        return "application/manifest+json"
    content_type, _encoding = mimetypes.guess_type(requested_path.name)
    return content_type or "application/octet-stream"

# Create your views here.

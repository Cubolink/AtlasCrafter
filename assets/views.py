import json
import mimetypes
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404

from accounts.models import ProjectMembership
from projects.models import Render


@login_required
def protected_render_asset(request, render_id: int, asset_path: str):
    render_obj = get_object_or_404(
        Render.objects.select_related("atlas__project"),
        id=render_id,
        is_enabled=True,
        atlas__is_active=True,
        atlas__project__is_active=True,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=render_obj.project)

    safe_path = PurePosixPath(asset_path)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        raise Http404("Asset not found")
    if is_other_map_asset(safe_path, render_obj):
        raise Http404("Asset not found")
    if safe_path == PurePosixPath("settings.json"):
        return scoped_viewer_settings(render_obj)

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
    internal_path = safe_path.as_posix()
    if not asset_file.is_file() and compressed_asset_file.is_file():
        asset_file = compressed_asset_file
        internal_path = f"{internal_path}.gz"
    if not asset_file.is_file():
        raise Http404("Asset not found")

    response = HttpResponse(content_type=content_type_for_requested_path(safe_path, asset_file))
    if asset_file.suffix == ".gz":
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


def is_other_map_asset(safe_path: PurePosixPath, render_obj: Render) -> bool:
    return (
        len(safe_path.parts) >= 2
        and safe_path.parts[0] == "maps"
        and safe_path.parts[1] not in allowed_viewer_map_ids(render_obj)
    )


def scoped_viewer_settings(render_obj: Render):
    settings_file = settings.BLUEMAP_WEBROOT_DIR / "settings.json"
    if not settings_file.is_file():
        raise Http404("Asset not found")

    with settings_file.open("r", encoding="utf-8") as file:
        viewer_settings = json.load(file)

    viewer_settings["maps"] = [resolve_viewer_map_id(render_obj, viewer_settings)]
    return JsonResponse(viewer_settings)


def resolve_viewer_map_id(render_obj: Render, viewer_settings: dict) -> str:
    allowed_map_ids = allowed_viewer_map_ids(render_obj)
    for map_id in viewer_settings.get("maps", []):
        if map_id in allowed_map_ids:
            return map_id
    return normalized_viewer_map_id(render_obj)


def allowed_viewer_map_ids(render_obj: Render) -> set[str]:
    return {render_obj.bluemap_map_id, normalized_viewer_map_id(render_obj)}


def normalized_viewer_map_id(render_obj: Render) -> str:
    return render_obj.bluemap_map_id.replace("-", "_")

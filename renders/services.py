import hashlib
import os
import shlex
import subprocess
from pathlib import Path

from django.db import transaction
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from accounts.models import ProjectMembership
from bluemap_configs.models import (
    BlueMapProfile,
    BlueMapRenderConfig,
    ConfigRevision,
    GeneratedConfigFile,
)
from projects.models import Render
from .models import RenderJob, RenderLogChunk


class RenderConfigurationError(RuntimeError):
    pass


ACTIVE_RENDER_STATUSES = [
    RenderJob.Status.QUEUED,
    RenderJob.Status.RUNNING,
]


def user_can_trigger_render(user, render: Render) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return ProjectMembership.objects.filter(
        user=user,
        project=render.project,
        role=ProjectMembership.Role.PROJECT_ADMINISTRATOR,
    ).exists()


def get_or_create_render_config(render: Render) -> BlueMapRenderConfig:
    if hasattr(render, "config"):
        return render.config

    profile = render.project.default_bluemap_profile or BlueMapProfile.objects.filter(
        is_active=True
    ).first()
    if profile is None:
        raise RenderConfigurationError(
            "No BlueMap profile is configured. Create one in Django Admin first."
        )
    return BlueMapRenderConfig.objects.create(render=render, profile=profile)


def preview_render_config(render: Render) -> tuple[BlueMapRenderConfig, str]:
    render_config = get_or_create_render_config(render)
    return render_config, render_config.generate_content()


def write_render_config(render_config: BlueMapRenderConfig, user=None) -> Path:
    ensure_bluemap_runtime_config()
    path = render_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    old_content = path.read_text(encoding="utf-8") if path.exists() else ""
    new_content = render_config.generate_content()
    path.write_text(new_content, encoding="utf-8")

    ConfigRevision.objects.create(
        render_config=render_config,
        old_content=old_content,
        new_content=new_content,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    render_config.last_generated_at = timezone.now()
    render_config.save(update_fields=["last_generated_at"])

    GeneratedConfigFile.objects.update_or_create(
        render_config=render_config,
        defaults={
            "path": str(path),
            "content_hash": hashlib.sha256(new_content.encode("utf-8")).hexdigest(),
            "last_written_at": timezone.now(),
        },
    )
    return path


def ensure_bluemap_runtime_config() -> None:
    settings.BLUEMAP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    settings.BLUEMAP_WEBROOT_DIR.mkdir(parents=True, exist_ok=True)
    (settings.BLUEMAP_CONFIG_DIR / "maps").mkdir(parents=True, exist_ok=True)
    (settings.BLUEMAP_CONFIG_DIR / "storages").mkdir(parents=True, exist_ok=True)

    write_managed_file(
        settings.BLUEMAP_CONFIG_DIR / "webapp.conf",
        (
            "## Managed by BlueMap Web UI Panel\n"
            "enabled: true\n"
            f'webroot: "{settings.BLUEMAP_WEBROOT_DIR.as_posix()}"\n'
            "update-settings-file: true\n"
            "use-cookies: true\n"
            "default-to-flat-view: false\n"
            "min-zoom-distance: 5\n"
            "max-zoom-distance: 100000\n"
            "resolution-default: 1\n"
            "hires-slider-max: 500\n"
            "hires-slider-default: 100\n"
            "hires-slider-min: 0\n"
            "lowres-slider-max: 7000\n"
            "lowres-slider-default: 2000\n"
            "lowres-slider-min: 500\n"
            "scripts: []\n"
            "styles: []\n"
        ),
    )
    write_managed_file(
        settings.BLUEMAP_CONFIG_DIR / "storages" / "file.conf",
        (
            "## Managed by BlueMap Web UI Panel\n"
            "storage-type: file\n"
            f'root: "{(settings.BLUEMAP_WEBROOT_DIR / "maps").as_posix()}"\n'
            "compression: gzip\n"
        ),
    )
    write_managed_file(
        settings.BLUEMAP_CONFIG_DIR / "webserver.conf",
        (
            "## Managed by BlueMap Web UI Panel\n"
            "enabled: true\n"
            f'webroot: "{settings.BLUEMAP_WEBROOT_DIR.as_posix()}"\n'
            "port: 8100\n"
            "log: {\n"
            '  file: "data/logs/webserver.log"\n'
            "  append: false\n"
            '  format: "%1$s \\"%3$s %4$s %5$s\\" %6$s %7$s"\n'
            "}\n"
        ),
    )


def write_managed_file(path: Path, content: str) -> None:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        is_managed = existing.startswith("## Managed by BlueMap Web UI Panel")
        is_bluemap_example = existing.startswith("##") and "BlueMap" in existing[:200]
        if not is_managed and not is_bluemap_example:
            return
    path.write_text(content, encoding="utf-8")


def build_command(render_config: BlueMapRenderConfig) -> list[str]:
    command_string = render_config.profile.command_template.format(**render_config.context())
    command = shlex.split(command_string, posix=os.name != "nt")
    command = [argument.strip('"') for argument in command]
    if command and command[0].lower().endswith(".jar"):
        command = [
            settings.BLUEMAP_JAVA_PATH,
            f"-Djava.io.tmpdir={settings.BLUEMAP_TMP_DIR.as_posix()}",
            "-jar",
            command[0],
            *command[1:],
        ]
    return command


def has_active_render_job(render: Render) -> bool:
    return render.jobs.filter(status__in=ACTIVE_RENDER_STATUSES).exists()


def cancel_queued_render_job(job: RenderJob, user=None) -> bool:
    if user is not None and not user_can_trigger_render(user, job.render):
        raise PermissionDenied("You do not have permission to cancel this Render job.")

    with transaction.atomic():
        locked_job = RenderJob.objects.select_for_update().get(id=job.id)
        if locked_job.status != RenderJob.Status.QUEUED:
            return False
        locked_job.status = RenderJob.Status.CANCELED
        locked_job.finished_at = timezone.now()
        locked_job.save(update_fields=["status", "finished_at", "updated_at"])
        return True


def enqueue_render(render: Render, requested_by=None) -> RenderJob:
    if requested_by is not None and not user_can_trigger_render(requested_by, render):
        raise PermissionDenied("You do not have permission to trigger this Render.")

    with transaction.atomic():
        if RenderJob.objects.select_for_update().filter(
            render=render,
            status__in=ACTIVE_RENDER_STATUSES,
        ).exists():
            raise RenderConfigurationError("This Render already has a queued or running job.")
        job = RenderJob.objects.create(render=render, requested_by=requested_by)

    return job


def run_render(render: Render, requested_by=None) -> RenderJob:
    job = RenderJob.objects.create(render=render, requested_by=requested_by)
    return execute_render_job(job)


def claim_next_queued_job(max_running: int | None = None) -> RenderJob | None:
    max_running = max_running or settings.BLUEMAP_RENDER_WORKER_CONCURRENCY
    if RenderJob.objects.filter(status=RenderJob.Status.RUNNING).count() >= max_running:
        return None

    with transaction.atomic():
        if RenderJob.objects.filter(status=RenderJob.Status.RUNNING).count() >= max_running:
            return None

        job = (
            RenderJob.objects.select_for_update()
            .select_related(
                "render__atlas__project",
                "render__atlas__world_folder",
                "requested_by",
            )
            .filter(status=RenderJob.Status.QUEUED)
            .order_by("created_at")
            .first()
        )
        if job is None:
            return None

        job.status = RenderJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])
        return job


def execute_render_job(job: RenderJob) -> RenderJob:
    render = job.render
    command = []
    try:
        render_config = get_or_create_render_config(render)
        write_render_config(render_config, job.requested_by)
        command = build_command(render_config)
        settings.BLUEMAP_TMP_DIR.mkdir(parents=True, exist_ok=True)
        process_env = os.environ.copy()
        process_env["TMP"] = str(settings.BLUEMAP_TMP_DIR)
        process_env["TEMP"] = str(settings.BLUEMAP_TMP_DIR)
        job.command = command
        job.status = RenderJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["command", "status", "started_at", "updated_at"])

        result = subprocess.run(
            command,
            cwd=Path(settings.BLUEMAP_CONFIG_DIR),
            capture_output=True,
            text=True,
            env=process_env,
            timeout=settings.BLUEMAP_RENDER_TIMEOUT_SECONDS,
            check=False,
        )
        if result.stdout:
            RenderLogChunk.objects.create(job=job, stream="stdout", content=result.stdout)
        if result.stderr:
            RenderLogChunk.objects.create(job=job, stream="stderr", content=result.stderr)

        job.exit_code = result.returncode
        job.status = (
            RenderJob.Status.SUCCEEDED
            if result.returncode == 0
            else RenderJob.Status.FAILED
        )
    except FileNotFoundError as exc:
        job.status = RenderJob.Status.FAILED
        job.exit_code = None
        missing_executable = exc.filename or (command[0] if command else settings.BLUEMAP_CLI_PATH)
        java_hint = ""
        if missing_executable == settings.BLUEMAP_JAVA_PATH:
            java_hint = (
                "\nThis Render uses a BlueMap .jar, so Java must be installed and "
                "available on PATH, or BLUEMAP_JAVA_PATH must point to java.exe."
            )
        RenderLogChunk.objects.create(
            job=job,
            stream="stderr",
            content=(
                f"Executable was not found: {missing_executable}\n"
                "Set BLUEMAP_CLI_PATH to the BlueMap executable or standalone CLI jar."
                f"{java_hint}"
            ),
        )
    except subprocess.TimeoutExpired as exc:
        job.status = RenderJob.Status.FAILED
        job.exit_code = None
        RenderLogChunk.objects.create(
            job=job,
            stream="stderr",
            content=f"BlueMap render timed out after {exc.timeout} seconds.",
        )
    except Exception as exc:
        job.status = RenderJob.Status.FAILED
        job.exit_code = None
        RenderLogChunk.objects.create(job=job, stream="stderr", content=str(exc))
    finally:
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "exit_code", "finished_at", "updated_at"])

    return job

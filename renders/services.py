import hashlib
import os
import shlex
import shutil
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
from projects.world_discovery import detect_server_minecraft_version, world_folder_exists
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
            "## Managed by AtlasCrafter\n"
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
            "## Managed by AtlasCrafter\n"
            "storage-type: file\n"
            f'root: "{(settings.BLUEMAP_WEBROOT_DIR / "maps").as_posix()}"\n'
            "compression: gzip\n"
        ),
    )
    write_managed_file(
        settings.BLUEMAP_CONFIG_DIR / "webserver.conf",
        (
            "## Managed by AtlasCrafter\n"
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
        is_managed = existing.startswith("## Managed by AtlasCrafter") or existing.startswith(
            "## Managed by BlueMap Web UI Panel"
        )
        is_bluemap_example = existing.startswith("##") and "BlueMap" in existing[:200]
        if not is_managed and not is_bluemap_example:
            return
    path.write_text(content, encoding="utf-8")


def build_command(
    render_config: BlueMapRenderConfig,
    *,
    force_render: bool = False,
) -> list[str]:
    command_string = render_config.profile.command_template.format(**render_config.context())
    command = shlex.split(command_string, posix=os.name != "nt")
    command = [argument.strip('"') for argument in command]
    command = add_bluemap_render_options(command, render_config.render)
    if force_render and not has_command_option(command, "-f", "--force-render"):
        command.append("--force-render")
    if command and command[0].lower().endswith(".jar"):
        command = [
            settings.BLUEMAP_JAVA_PATH,
            f"-Djava.io.tmpdir={settings.BLUEMAP_TMP_DIR.as_posix()}",
            "-jar",
            command[0],
            *command[1:],
        ]
    return command


def add_bluemap_render_options(command: list[str], render: Render) -> list[str]:
    command = list(command)
    if not has_command_option(command, "-m", "--maps"):
        command.extend(["--maps", render.bluemap_map_id.replace("-", "_")])

    mods_path, minecraft_version = resolve_render_resources(render)
    if mods_path is not None:
        if not has_command_option(command, "-n", "--mods"):
            command.extend(["--mods", mods_path.as_posix()])

    if minecraft_version and not has_command_option(command, "-v", "--mc-version"):
        command.extend(["--mc-version", minecraft_version])

    return command


def resolve_render_resources(render: Render) -> tuple[Path | None, str | None]:
    world = render.world_folder
    inherited_source = world.default_resource_source
    if inherited_source is None and world.minecraft_server_id:
        inherited_source = world.minecraft_server.resource_source

    source = inherited_source
    load_mods = False
    if render.resource_mode == Render.ResourceMode.SOURCE:
        source = render.resource_source
        load_mods = source is not None
    elif render.resource_mode == Render.ResourceMode.CUSTOM:
        mods_path = Path(render.custom_mods_path) if render.custom_mods_path else None
        return valid_mods_path(mods_path), render.minecraft_version_override or None
    elif render.resource_mode == Render.ResourceMode.DISABLED:
        load_mods = False
    elif source is not None:
        load_mods = source.load_mod_resources_by_default

    minecraft_version = render.minecraft_version_override or (
        source.minecraft_version if source else None
    )
    mods_path = valid_mods_path(Path(source.mods_path)) if source and load_mods else None
    if source is not None or render.resource_mode == Render.ResourceMode.DISABLED:
        return mods_path, minecraft_version

    server_root = discover_server_root(Path(world.source_path))
    if server_root is None:
        return None, minecraft_version
    return valid_mods_path(server_root / "mods"), (
        minecraft_version or detect_server_minecraft_version(server_root)
    )


def valid_mods_path(path: Path | None) -> Path | None:
    if path is None or not path.is_dir() or not any(path.glob("*.jar")):
        return None
    return path


def has_command_option(command: list[str], *options: str) -> bool:
    return any(
        argument in options
        or any(argument.startswith(f"{option}=") for option in options)
        for argument in command
    )


def discover_server_root(world_path: Path) -> Path | None:
    source_root = Path(settings.SOURCE_WORLDS_DIR).resolve()
    current = world_path.resolve()

    for _ in range(5):
        has_mods = (current / "mods").is_dir()
        has_minecraft_libraries = (
            current / "libraries" / "net" / "minecraft" / "server"
        ).is_dir()
        if has_mods or has_minecraft_libraries:
            return current
        if current == source_root or current.parent == current:
            break
        current = current.parent

    return None


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


def enqueue_render(
    render: Render,
    requested_by=None,
    operation: str = RenderJob.Operation.UPDATE,
) -> RenderJob:
    if requested_by is not None and not user_can_trigger_render(requested_by, render):
        raise PermissionDenied("You do not have permission to trigger this Render.")
    if operation not in RenderJob.Operation.values:
        raise RenderConfigurationError(f"Unsupported Render job operation: {operation}")

    if not render_world_folder_is_available(render):
        job = RenderJob.objects.create(
            render=render,
            requested_by=requested_by,
            operation=operation,
            status=RenderJob.Status.FAILED,
            finished_at=timezone.now(),
        )
        log_world_folder_unavailable(render, job)
        return job

    with transaction.atomic():
        if RenderJob.objects.select_for_update().filter(
            render=render,
            status__in=ACTIVE_RENDER_STATUSES,
        ).exists():
            raise RenderConfigurationError("This Render already has a queued or running job.")
        job = RenderJob.objects.create(
            render=render,
            requested_by=requested_by,
            operation=operation,
        )

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
            RenderJob.objects.select_for_update(of=("self",))
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
    rebuild_paths = []
    try:
        if not render_world_folder_is_available(render):
            log_world_folder_unavailable(render, job)
            job.status = RenderJob.Status.FAILED
            job.exit_code = None
            return job

        render_config = get_or_create_render_config(render)
        write_render_config(render_config, job.requested_by)
        command = build_command(
            render_config,
            force_render=job.operation == RenderJob.Operation.REBUILD,
        )
        settings.BLUEMAP_TMP_DIR.mkdir(parents=True, exist_ok=True)
        process_env = os.environ.copy()
        process_env["TMP"] = str(settings.BLUEMAP_TMP_DIR)
        process_env["TEMP"] = str(settings.BLUEMAP_TMP_DIR)
        job.command = command
        job.status = RenderJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["command", "status", "started_at", "updated_at"])

        if job.operation == RenderJob.Operation.REBUILD:
            rebuild_paths = stage_render_output_rebuild(render, job)

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
        if rebuild_paths:
            try:
                if job.status == RenderJob.Status.SUCCEEDED:
                    discard_render_output_backups(rebuild_paths)
                else:
                    restore_render_output_backups(rebuild_paths)
            except Exception as exc:
                job.status = RenderJob.Status.FAILED
                RenderLogChunk.objects.create(
                    job=job,
                    stream="stderr",
                    content=f"Could not finalize the Render rebuild: {exc}",
                )
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "exit_code", "finished_at", "updated_at"])

    return job


def stage_render_output_rebuild(render: Render, job: RenderJob) -> list[tuple[Path, Path | None]]:
    maps_root = (settings.BLUEMAP_WEBROOT_DIR / "maps").resolve()
    maps_root.mkdir(parents=True, exist_ok=True)
    staged_paths = []

    try:
        for map_id in bluemap_output_map_ids(render):
            candidate = maps_root / map_id
            if candidate.is_symlink():
                raise RenderConfigurationError(
                    f"Refusing to rebuild symlinked BlueMap output path: {candidate}"
                )

            target = candidate.resolve(strict=False)
            if target.parent != maps_root:
                raise RenderConfigurationError(
                    f"Refusing to rebuild unsafe BlueMap output path: {target}"
                )

            backup = maps_root / f".rebuild-job-{job.id}-{map_id}"
            if backup.exists() or backup.is_symlink():
                raise RenderConfigurationError(
                    f"A previous rebuild backup already exists: {backup}"
                )

            if target.exists():
                if not target.is_dir():
                    raise RenderConfigurationError(
                        f"BlueMap output path is not a directory: {target}"
                    )
                target.replace(backup)
                staged_paths.append((target, backup))
            else:
                staged_paths.append((target, None))

        replaced = [target.name for target, backup in staged_paths if backup is not None]
        detail = ", ".join(replaced) if replaced else "no previous map output"
        RenderLogChunk.objects.create(
            job=job,
            stream="stdout",
            content=f"Starting full Render rebuild; staged {detail}.",
        )
    except Exception:
        restore_render_output_backups(staged_paths)
        raise

    return staged_paths


def restore_render_output_backups(staged_paths: list[tuple[Path, Path | None]]) -> None:
    for target, backup in reversed(staged_paths):
        remove_render_output_path(target)
        if backup is not None and backup.exists():
            backup.replace(target)


def discard_render_output_backups(staged_paths: list[tuple[Path, Path | None]]) -> None:
    for _, backup in staged_paths:
        if backup is not None:
            remove_render_output_path(backup)


def remove_render_output_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_dir():
        raise RenderConfigurationError(f"Refusing to remove unsafe BlueMap output path: {path}")
    shutil.rmtree(path)


def bluemap_output_map_ids(render: Render) -> list[str]:
    return sorted({render.bluemap_map_id, render.bluemap_map_id.replace("-", "_")})


def render_world_folder_is_available(render: Render) -> bool:
    return render.atlas.world_folder.is_active and world_folder_exists(render.atlas.world_folder)


def log_world_folder_unavailable(render: Render, job: RenderJob) -> None:
    world = render.atlas.world_folder
    if not world.is_active:
        RenderLogChunk.objects.create(
            job=job,
            stream="stderr",
            content=(
                "The Minecraft world folder for this Render is archived. "
                "Restore the World Folder before triggering new render jobs."
            ),
        )
        return

    mark_world_folder_missing(render, job)


def mark_world_folder_missing(render: Render, job: RenderJob) -> None:
    world = render.atlas.world_folder
    if world.is_active:
        world.is_active = False
        world.save(update_fields=["is_active", "updated_at"])
    RenderLogChunk.objects.create(
        job=job,
        stream="stderr",
        content=(
            "The Minecraft world folder for this Render was not found on disk. "
            f"Expected level.dat at: {Path(world.source_path) / 'level.dat'}\n"
            "The World Folder has been archived so it cannot be selected for new Atlases."
        ),
    )

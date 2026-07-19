from tempfile import TemporaryDirectory
from pathlib import Path

from django.test import TestCase, override_settings

from bluemap_configs.models import BlueMapProfile
from projects.models import (
    Atlas,
    MinecraftResourceSource,
    Project,
    ProjectVisibleWorld,
    Render,
    WorldFolder,
)
from .models import RenderJob
from .services import (
    RenderConfigurationError,
    build_command,
    claim_next_queued_job,
    enqueue_render,
    execute_render_job,
    get_or_create_render_config,
    run_render,
)


class RenderRunnerTests(TestCase):
    def create_render(self):
        suffix = BlueMapProfile.objects.count() + 1
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        world_path = Path(temp_dir.name) / f"world-{suffix}"
        world_path.mkdir()
        (world_path / "level.dat").write_bytes(b"")
        profile = BlueMapProfile.objects.create(
            name=f"Default {suffix}",
            slug=f"default-{suffix}",
        )
        project = Project.objects.create(
            name=f"Survival Server {suffix}",
            default_bluemap_profile=profile,
        )
        world = WorldFolder.objects.create(
            display_name=f"Overworld {suffix}",
            source_path=str(world_path.resolve()),
        )
        ProjectVisibleWorld.objects.create(project=project, world_folder=world)
        atlas = Atlas.objects.create(
            project=project,
            world_folder=world,
            display_name="Overworld",
        )
        return Render.objects.create(
            atlas=atlas,
            bluemap_map_id=f"overworld-hd-{suffix}",
            display_name="HD 4K",
            dimension=Render.Dimension.OVERWORLD,
        )

    def test_missing_bluemap_executable_creates_failed_job_with_log(self):
        with TemporaryDirectory() as config_dir, TemporaryDirectory() as webroot_dir:
            with override_settings(
                BLUEMAP_CLI_PATH="definitely-not-installed-bluemap",
                BLUEMAP_CONFIG_DIR=Path(config_dir),
                BLUEMAP_WEBROOT_DIR=Path(webroot_dir),
            ):
                render = self.create_render()

                job = run_render(render)

                self.assertEqual(job.status, RenderJob.Status.FAILED)
                self.assertTrue(job.log_chunks.filter(content__contains="not found").exists())
                self.assertTrue(render.config.generated_file.path.endswith("overworld-hd-1.conf"))

    def test_jar_cli_path_builds_java_command(self):
        with TemporaryDirectory() as config_dir, TemporaryDirectory() as webroot_dir:
            with override_settings(
                BLUEMAP_CLI_PATH="C:/Tools/BlueMap-cli.jar",
                BLUEMAP_JAVA_PATH="java",
                BLUEMAP_CONFIG_DIR=Path(config_dir),
                BLUEMAP_WEBROOT_DIR=Path(webroot_dir),
            ):
                render = self.create_render()
                render_config = get_or_create_render_config(render)

                command = build_command(render_config)

                self.assertEqual(command[0], "java")
                self.assertEqual(command[2:4], ["-jar", "C:/Tools/BlueMap-cli.jar"])
                self.assertTrue(command[1].startswith("-Djava.io.tmpdir="))
                self.assertIn("-c", command)
                self.assertIn(str(Path(config_dir).as_posix()), command)

    def test_jar_cli_path_uses_configured_java_path(self):
        with TemporaryDirectory() as config_dir, TemporaryDirectory() as webroot_dir:
            with override_settings(
                BLUEMAP_CLI_PATH="C:/Tools/BlueMap-cli.jar",
                BLUEMAP_JAVA_PATH="C:/Java/bin/java.exe",
                BLUEMAP_CONFIG_DIR=Path(config_dir),
                BLUEMAP_WEBROOT_DIR=Path(webroot_dir),
            ):
                render = self.create_render()
                render_config = get_or_create_render_config(render)

                command = build_command(render_config)

                self.assertEqual(command[0], "C:/Java/bin/java.exe")
                self.assertEqual(command[2:4], ["-jar", "C:/Tools/BlueMap-cli.jar"])

    def test_build_command_discovers_forge_mods_and_minecraft_version(self):
        with TemporaryDirectory() as config_dir, TemporaryDirectory() as webroot_dir:
            with override_settings(
                BLUEMAP_CLI_PATH="C:/Tools/BlueMap-cli.jar",
                BLUEMAP_JAVA_PATH="java",
                BLUEMAP_CONFIG_DIR=Path(config_dir),
                BLUEMAP_WEBROOT_DIR=Path(webroot_dir),
            ):
                render = self.create_render()
                world_path = Path(render.world_folder.source_path)
                server_root = world_path.parent
                mods_path = server_root / "mods"
                mods_path.mkdir()
                (mods_path / "create.jar").write_bytes(b"")
                (server_root / "libraries" / "net" / "minecraft" / "server" / "1.20.1").mkdir(
                    parents=True
                )
                render_config = get_or_create_render_config(render)

                command = build_command(render_config)

                self.assertEqual(command[command.index("--mods") + 1], mods_path.as_posix())
                self.assertEqual(command[command.index("--mc-version") + 1], "1.20.1")
                self.assertEqual(
                    command[command.index("--maps") + 1],
                    render.bluemap_map_id.replace("-", "_"),
                )

    def test_build_command_uses_registered_world_resource_source(self):
        render = self.create_render()
        world_path = Path(render.world_folder.source_path)
        mods_path = world_path.parent / "registered-mods"
        mods_path.mkdir()
        (mods_path / "create.jar").write_bytes(b"")
        source = MinecraftResourceSource.objects.create(
            display_name="Create Pack",
            root_path=str(world_path.parent),
            mods_path=str(mods_path),
            minecraft_version="1.20.1",
            mod_loader=MinecraftResourceSource.ModLoader.FORGE,
        )
        render.world_folder.default_resource_source = source
        render.world_folder.save(update_fields=["default_resource_source"])
        render_config = get_or_create_render_config(render)

        command = build_command(render_config)

        self.assertEqual(command[command.index("--mods") + 1], mods_path.as_posix())
        self.assertEqual(command[command.index("--mc-version") + 1], "1.20.1")

    def test_build_command_can_disable_inherited_mod_resources(self):
        render = self.create_render()
        world_path = Path(render.world_folder.source_path)
        mods_path = world_path.parent / "disabled-mods"
        mods_path.mkdir()
        (mods_path / "create.jar").write_bytes(b"")
        source = MinecraftResourceSource.objects.create(
            display_name="Create Pack",
            root_path=str(world_path.parent),
            mods_path=str(mods_path),
            minecraft_version="1.20.1",
        )
        render.world_folder.default_resource_source = source
        render.world_folder.save(update_fields=["default_resource_source"])
        render.resource_mode = Render.ResourceMode.DISABLED
        render.save(update_fields=["resource_mode"])
        render_config = get_or_create_render_config(render)

        command = build_command(render_config)

        self.assertNotIn("--mods", command)
        self.assertEqual(command[command.index("--mc-version") + 1], "1.20.1")

    def test_enqueue_render_rejects_existing_active_job(self):
        render = self.create_render()
        RenderJob.objects.create(render=render, status=RenderJob.Status.RUNNING)

        with self.assertRaises(RenderConfigurationError):
            enqueue_render(render)

        self.assertEqual(render.jobs.count(), 1)

    def test_enqueue_render_leaves_job_queued_for_worker(self):
        render = self.create_render()

        job = enqueue_render(render)

        self.assertEqual(job.status, RenderJob.Status.QUEUED)
        self.assertIsNone(job.started_at)

    def test_enqueue_render_fails_and_archives_world_when_world_folder_is_missing(self):
        render = self.create_render()
        world = render.atlas.world_folder
        (Path(world.source_path) / "level.dat").unlink()

        job = enqueue_render(render)

        self.assertEqual(job.status, RenderJob.Status.FAILED)
        self.assertTrue(job.log_chunks.filter(content__contains="not found on disk").exists())
        world.refresh_from_db()
        self.assertFalse(world.is_active)

    def test_enqueue_render_fails_when_world_folder_is_archived(self):
        render = self.create_render()
        world = render.atlas.world_folder
        world.is_active = False
        world.save(update_fields=["is_active"])

        job = enqueue_render(render)

        self.assertEqual(job.status, RenderJob.Status.FAILED)
        self.assertTrue(job.log_chunks.filter(content__contains="world folder for this Render is archived").exists())
        world.refresh_from_db()
        self.assertFalse(world.is_active)

    def test_execute_render_job_fails_and_archives_world_when_world_folder_disappears(self):
        render = self.create_render()
        world = render.atlas.world_folder
        job = RenderJob.objects.create(render=render, status=RenderJob.Status.RUNNING)
        (Path(world.source_path) / "level.dat").unlink()

        job = execute_render_job(job)

        self.assertEqual(job.status, RenderJob.Status.FAILED)
        self.assertTrue(job.log_chunks.filter(content__contains="World Folder has been archived").exists())
        world.refresh_from_db()
        self.assertFalse(world.is_active)

    def test_execute_render_job_fails_when_world_folder_is_archived(self):
        render = self.create_render()
        world = render.atlas.world_folder
        world.is_active = False
        world.save(update_fields=["is_active"])
        job = RenderJob.objects.create(render=render, status=RenderJob.Status.RUNNING)

        job = execute_render_job(job)

        self.assertEqual(job.status, RenderJob.Status.FAILED)
        self.assertTrue(job.log_chunks.filter(content__contains="Restore the World Folder").exists())

    def test_claim_next_queued_job_respects_global_running_limit(self):
        first_render = self.create_render()
        second_render = self.create_render()
        RenderJob.objects.create(render=first_render, status=RenderJob.Status.RUNNING)
        RenderJob.objects.create(render=second_render, status=RenderJob.Status.QUEUED)

        claimed = claim_next_queued_job(max_running=1)

        self.assertIsNone(claimed)

    def test_claim_next_queued_job_marks_oldest_job_running(self):
        render = self.create_render()
        job = RenderJob.objects.create(render=render, status=RenderJob.Status.QUEUED)

        claimed = claim_next_queued_job(max_running=1)

        self.assertEqual(claimed.id, job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, RenderJob.Status.RUNNING)
        self.assertIsNotNone(job.started_at)

# Create your tests here.

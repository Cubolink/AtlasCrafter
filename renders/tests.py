from tempfile import TemporaryDirectory
from pathlib import Path

from django.test import TestCase, override_settings

from bluemap_configs.models import BlueMapProfile
from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from .models import RenderJob
from .services import build_command, get_or_create_render_config, run_render


class RenderRunnerTests(TestCase):
    def create_render(self):
        profile = BlueMapProfile.objects.create(name="Default", slug="default")
        project = Project.objects.create(
            name="Survival Server",
            default_bluemap_profile=profile,
        )
        world = WorldFolder.objects.create(
            display_name="Overworld",
            source_path="/srv/minecraft/world",
        )
        ProjectVisibleWorld.objects.create(project=project, world_folder=world)
        atlas = Atlas.objects.create(
            project=project,
            world_folder=world,
            display_name="Overworld",
        )
        return Render.objects.create(
            atlas=atlas,
            bluemap_map_id="overworld-hd",
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
                self.assertTrue(render.config.generated_file.path.endswith("overworld-hd.conf"))

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

# Create your tests here.

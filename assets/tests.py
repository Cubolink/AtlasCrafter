from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder


class ProtectedRenderAssetTests(TestCase):
    def test_asset_can_be_framed_by_same_origin_page(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            (webroot / "index.html").write_text("<html>BlueMap</html>", encoding="utf-8")

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin",
                    email="admin@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server")
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
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client()
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={"render_id": render.id, "asset_path": "index.html"},
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
                response.close()

    def test_gzipped_json_asset_sets_json_and_gzip_headers(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            map_dir = webroot / "maps" / "overworld"
            map_dir.mkdir(parents=True)
            (map_dir / "textures.json.gz").write_bytes(b"\x1f\x8b\x08\x00")

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin",
                    email="admin@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server")
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
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client()
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={
                            "render_id": render.id,
                            "asset_path": "maps/overworld/textures.json.gz",
                        },
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"], "application/json")
                self.assertEqual(response.headers["Content-Encoding"], "gzip")
                response.close()

    def test_json_request_falls_back_to_gzipped_json_file(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            map_dir = webroot / "maps" / "overworld"
            map_dir.mkdir(parents=True)
            (map_dir / "textures.json.gz").write_bytes(b"\x1f\x8b\x08\x00")

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin2",
                    email="admin2@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 2")
                world = WorldFolder.objects.create(
                    display_name="Overworld 2",
                    source_path="/srv/minecraft/world2",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 2",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client()
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={
                            "render_id": render.id,
                            "asset_path": "maps/overworld/textures.json",
                        },
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"], "application/json")
                self.assertEqual(response.headers["Content-Encoding"], "gzip")
                response.close()

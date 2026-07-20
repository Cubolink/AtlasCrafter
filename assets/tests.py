import json
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

    def test_x_accel_asset_sets_content_type_headers(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            asset_dir = webroot / "assets"
            asset_dir.mkdir(parents=True)
            (asset_dir / "index.js").write_text("console.log('BlueMap')", encoding="utf-8")

            with override_settings(
                DEBUG=False,
                BLUEMAP_WEBROOT_DIR=webroot,
                INTERNAL_ACCEL_ROOT="/_protected_bluemap/",
            ):
                user = User.objects.create_superuser(
                    username="admin7",
                    email="admin7@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 7")
                world = WorldFolder.objects.create(
                    display_name="Overworld 7",
                    source_path="/srv/minecraft/world7",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 7",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client(HTTP_HOST="localhost")
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={"render_id": render.id, "asset_path": "assets/index.js"},
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("javascript", response.headers["Content-Type"])
                self.assertEqual(response.headers["X-Accel-Redirect"], "/_protected_bluemap/assets/index.js")

    def test_x_accel_asset_falls_back_to_gzip_headers(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            asset_dir = webroot / "maps" / "overworld"
            asset_dir.mkdir(parents=True)
            (asset_dir / "textures.json.gz").write_bytes(b"\x1f\x8b\x08\x00")

            with override_settings(
                DEBUG=False,
                BLUEMAP_WEBROOT_DIR=webroot,
                INTERNAL_ACCEL_ROOT="/_protected_bluemap/",
            ):
                user = User.objects.create_superuser(
                    username="admin8",
                    email="admin8@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 8")
                world = WorldFolder.objects.create(
                    display_name="Overworld 8",
                    source_path="/srv/minecraft/world8",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 8",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client(HTTP_HOST="localhost")
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
                self.assertEqual(
                    response.headers["X-Accel-Redirect"],
                    "/_protected_bluemap/maps/overworld/textures.json.gz",
                )

    def test_root_viewer_settings_are_scoped_to_requested_render(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            (webroot / "settings.json").write_text(
                json.dumps(
                    {
                        "version": "5.22",
                        "mapDataRoot": "maps",
                        "liveDataRoot": "maps",
                        "maps": ["overworld", "nether_render"],
                    }
                ),
                encoding="utf-8",
            )

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin3",
                    email="admin3@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 3")
                world = WorldFolder.objects.create(
                    display_name="Overworld 3",
                    source_path="/srv/minecraft/world3",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 3",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="nether-render",
                    display_name="Nether",
                    dimension=Render.Dimension.NETHER,
                )

                client = Client()
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={"render_id": render.id, "asset_path": "settings.json"},
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["maps"], ["nether_render"])

    def test_root_viewer_settings_fall_back_to_normalized_render_id(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            (webroot / "settings.json").write_text(
                json.dumps(
                    {
                        "version": "5.22",
                        "mapDataRoot": "maps",
                        "liveDataRoot": "maps",
                        "maps": ["other_map"],
                    }
                ),
                encoding="utf-8",
            )

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin5",
                    email="admin5@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 5")
                world = WorldFolder.objects.create(
                    display_name="Overworld 5",
                    source_path="/srv/minecraft/world5",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 5",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="render-1234",
                    display_name="Overworld",
                    dimension=Render.Dimension.OVERWORLD,
                )

                client = Client()
                client.force_login(user)
                response = client.get(
                    reverse(
                        "protected_render_asset",
                        kwargs={"render_id": render.id, "asset_path": "settings.json"},
                    )
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["maps"], ["render_1234"])

    def test_render_asset_endpoint_blocks_other_map_assets(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            other_map_dir = webroot / "maps" / "nether"
            other_map_dir.mkdir(parents=True)
            (other_map_dir / "settings.json").write_text("{}", encoding="utf-8")

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin4",
                    email="admin4@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 4")
                world = WorldFolder.objects.create(
                    display_name="Overworld 4",
                    source_path="/srv/minecraft/world4",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 4",
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
                            "asset_path": "maps/nether/settings.json",
                        },
                    )
                )

                self.assertEqual(response.status_code, 404)

    def test_render_asset_endpoint_allows_normalized_map_asset(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            map_dir = webroot / "maps" / "overworld_render"
            map_dir.mkdir(parents=True)
            (map_dir / "settings.json").write_text("{}", encoding="utf-8")

            with override_settings(DEBUG=True, BLUEMAP_WEBROOT_DIR=webroot):
                user = User.objects.create_superuser(
                    username="admin6",
                    email="admin6@example.com",
                    password="password",
                )
                project = Project.objects.create(name="Survival Server 6")
                world = WorldFolder.objects.create(
                    display_name="Overworld 6",
                    source_path="/srv/minecraft/world6",
                )
                ProjectVisibleWorld.objects.create(project=project, world_folder=world)
                atlas = Atlas.objects.create(
                    project=project,
                    world_folder=world,
                    display_name="Overworld 6",
                )
                render = Render.objects.create(
                    atlas=atlas,
                    bluemap_map_id="overworld-render",
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
                            "asset_path": "maps/overworld_render/settings.json",
                        },
                    )
                )

                self.assertEqual(response.status_code, 200)
                response.close()

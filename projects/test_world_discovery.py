from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import MinecraftResourceSource, MinecraftServer, WorldFolder
from .world_discovery import (
    DIMENSION_END,
    DIMENSION_NETHER,
    DIMENSION_OVERWORLD,
    build_world_tree,
    scan_source_worlds,
)


class WorldDiscoveryTests(TestCase):
    def test_scan_source_worlds_discovers_nested_worlds_and_dimensions(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            world = source_root / "worlds_from_aternos" / "Survival"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"")
            (world / "DIM-1").mkdir()
            (world / "DIM1").mkdir()

            result = scan_source_worlds(source_root)

            self.assertEqual(len(result.created), 1)
            discovered = WorldFolder.objects.get()
            self.assertEqual(discovered.display_name, "Survival")
            self.assertEqual(discovered.source_path, str(world.resolve()))
            self.assertEqual(
                discovered.detected_dimensions,
                [DIMENSION_OVERWORLD, DIMENSION_NETHER, DIMENSION_END],
            )

    def test_scan_source_worlds_updates_existing_dimensions(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            world = source_root / "Survival"
            world.mkdir()
            (world / "level.dat").write_bytes(b"")
            existing = WorldFolder.objects.create(
                display_name="Survival",
                source_path=str(world.resolve()),
                detected_dimensions=[],
            )

            result = scan_source_worlds(source_root)

            self.assertEqual(len(result.updated), 1)
            existing.refresh_from_db()
            self.assertEqual(existing.detected_dimensions, [DIMENSION_OVERWORLD])

    def test_scan_detects_forge_server_and_assigns_its_resources(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            server_root = source_root / "create-server"
            world = server_root / "world"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"")
            (server_root / "server.properties").write_text("level-name=world", encoding="utf-8")
            mods_path = server_root / "mods"
            mods_path.mkdir()
            (mods_path / "create.jar").write_bytes(b"")
            (server_root / "libraries" / "net" / "minecraft" / "server" / "1.20.1").mkdir(
                parents=True
            )
            (server_root / "libraries" / "net" / "minecraftforge").mkdir(parents=True)

            result = scan_source_worlds(source_root)

            server = MinecraftServer.objects.get()
            source = MinecraftResourceSource.objects.get()
            discovered_world = WorldFolder.objects.get()
            self.assertEqual(result.servers, [server])
            self.assertEqual(server.resource_source, source)
            self.assertEqual(source.minecraft_version, "1.20.1")
            self.assertEqual(source.mod_loader, MinecraftResourceSource.ModLoader.FORGE)
            self.assertEqual(source.mods_path, str(mods_path))
            self.assertEqual(discovered_world.minecraft_server, server)
            self.assertEqual(discovered_world.default_resource_source, source)

            tree = build_world_tree([discovered_world], source_root, [source])
            self.assertEqual(tree["children"]["create-server"]["server"], server)
            self.assertEqual(
                tree["children"]["create-server"]["children"]["mods"]["resource_sources"],
                [source],
            )

    def test_scan_assigns_standalone_world_to_modpack_resources(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            instance_root = source_root / "personal-instance"
            world = instance_root / "saves" / "Creative"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"")
            mods_path = instance_root / "mods"
            mods_path.mkdir()
            (mods_path / "example.jar").write_bytes(b"")

            scan_source_worlds(source_root)

            source = MinecraftResourceSource.objects.get()
            discovered_world = WorldFolder.objects.get()
            self.assertFalse(MinecraftServer.objects.exists())
            self.assertEqual(source.source_type, MinecraftResourceSource.SourceType.MODPACK)
            self.assertEqual(discovered_world.default_resource_source, source)
            self.assertIsNone(discovered_world.minecraft_server)

    def test_scan_source_worlds_archives_missing_known_worlds_under_source_root(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            missing_world = source_root / "MissingWorld"
            existing = WorldFolder.objects.create(
                display_name="Missing World",
                source_path=str(missing_world.resolve()),
                is_active=True,
            )

            result = scan_source_worlds(source_root)

            existing.refresh_from_db()
            self.assertFalse(existing.is_active)
            self.assertEqual(result.archived, [existing])

    def test_scan_source_worlds_restores_rediscovered_world(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            world = source_root / "Survival"
            world.mkdir()
            (world / "level.dat").write_bytes(b"")
            existing = WorldFolder.objects.create(
                display_name="Survival",
                source_path=str(world.resolve()),
                is_active=False,
            )

            result = scan_source_worlds(source_root)

            existing.refresh_from_db()
            self.assertTrue(existing.is_active)
            self.assertEqual(result.restored, [existing])

    def test_build_world_tree_groups_worlds_by_parent_folder(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            aternos = WorldFolder.objects.create(
                display_name="World A",
                source_path=str((source_root / "worlds_from_aternos" / "World_A").resolve()),
            )
            survival = WorldFolder.objects.create(
                display_name="Season 1",
                source_path=str((source_root / "survival_worlds" / "Season_1").resolve()),
            )

            tree = build_world_tree([aternos, survival], source_root)

            self.assertIn("worlds_from_aternos", tree["children"])
            self.assertIn("survival_worlds", tree["children"])
            self.assertEqual(
                tree["children"]["worlds_from_aternos"]["worlds"],
                [aternos],
            )


class WorldFolderViewsTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="superadmin",
            password="password-123",
        )
        self.staff = User.objects.create_user(
            username="staff",
            password="password-123",
            is_staff=True,
        )
        self.client = Client(HTTP_HOST="localhost")

    def test_world_folders_page_requires_superuser(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("world_folders"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_superuser_can_scan_world_folders_from_page(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            world = source_root / "group" / "Survival"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"")
            self.client.force_login(self.superuser)

            with override_settings(SOURCE_WORLDS_DIR=source_root):
                response = self.client.post(reverse("scan_world_folders"))

            self.assertEqual(response.status_code, 302)
            self.assertTrue(WorldFolder.objects.filter(display_name="Survival").exists())

    def test_world_folders_page_shows_tree_and_table(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            world_path = source_root / "worlds_from_aternos" / "World_A"
            world_path.mkdir(parents=True)
            WorldFolder.objects.create(
                display_name="World A",
                source_path=str(world_path.resolve()),
                detected_dimensions=[DIMENSION_OVERWORLD],
            )
            self.client.force_login(self.superuser)

            with override_settings(SOURCE_WORLDS_DIR=source_root):
                response = self.client.get(reverse("world_folders"))

            self.assertContains(response, "worlds_from_aternos")
            self.assertContains(response, "World A")
            self.assertContains(response, DIMENSION_OVERWORLD)

    def test_sources_page_marks_detected_server_in_tree(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            server_root = source_root / "ICGO"
            world_path = server_root / "world"
            world_path.mkdir(parents=True)
            (world_path / "level.dat").write_bytes(b"")
            (server_root / "server.properties").write_text("level-name=world", encoding="utf-8")
            mods_path = server_root / "mods"
            mods_path.mkdir()
            (mods_path / "create.jar").write_bytes(b"")
            self.client.force_login(self.superuser)

            with override_settings(SOURCE_WORLDS_DIR=source_root):
                scan_source_worlds(source_root)
                response = self.client.get(reverse("world_folders"))

            self.assertContains(response, "Detected Servers")
            self.assertContains(response, "ICGO")
            self.assertContains(response, "Resource Sources")
            self.assertContains(response, "server")

    def test_superuser_can_add_world_folder_manually(self):
        with TemporaryDirectory() as source_dir:
            world_path = Path(source_dir) / "ManualWorld"
            world_path.mkdir()
            (world_path / "level.dat").write_bytes(b"")
            self.client.force_login(self.superuser)

            response = self.client.post(
                reverse("create_world_folder"),
                {
                    "display_name": "Manual World",
                    "source_path": str(world_path),
                    "is_active": "on",
                    "notes": "Imported by hand",
                },
            )

            self.assertEqual(response.status_code, 302)
            world = WorldFolder.objects.get(display_name="Manual World")
            self.assertEqual(world.detected_dimensions, [DIMENSION_OVERWORLD])

    def test_superuser_can_register_resource_source_from_allowed_root(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as resources_dir:
            mods_path = Path(resources_dir) / "create-pack" / "mods"
            mods_path.mkdir(parents=True)
            (mods_path / "create.jar").write_bytes(b"")
            self.client.force_login(self.superuser)

            with override_settings(
                SOURCE_WORLDS_DIR=Path(source_dir),
                BLUEMAP_RESOURCE_SOURCES_DIR=Path(resources_dir),
            ):
                response = self.client.post(
                    reverse("create_resource_source"),
                    {
                        "display_name": "Personal Create",
                        "root_path": str(mods_path.parent),
                        "mods_path": str(mods_path),
                        "minecraft_version": "1.20.1",
                        "mod_loader": MinecraftResourceSource.ModLoader.FORGE,
                        "load_mod_resources_by_default": "on",
                        "is_active": "on",
                        "notes": "Local modpack",
                    },
                )
                sources_response = self.client.get(reverse("world_folders"))

            self.assertEqual(response.status_code, 302)
            source = MinecraftResourceSource.objects.get()
            self.assertEqual(source.display_name, "Personal Create")
            self.assertFalse(source.auto_detect)
            self.assertContains(sources_response, "Additional Resource Root")
            self.assertContains(sources_response, "Personal Create")

    def test_superuser_can_archive_world_folder(self):
        world = WorldFolder.objects.create(
            display_name="Archive Me",
            source_path="/srv/worlds/archive-me",
            is_active=True,
        )
        self.client.force_login(self.superuser)

        response = self.client.post(reverse("archive_world_folder", kwargs={"world_id": world.id}))

        self.assertEqual(response.status_code, 302)
        world.refresh_from_db()
        self.assertFalse(world.is_active)

    def test_superuser_can_restore_world_folder_when_path_exists(self):
        with TemporaryDirectory() as source_dir:
            world_path = Path(source_dir) / "ArchivedWorld"
            world_path.mkdir()
            (world_path / "level.dat").write_bytes(b"")
            world = WorldFolder.objects.create(
                display_name="Archived World",
                source_path=str(world_path.resolve()),
                is_active=False,
            )
            self.client.force_login(self.superuser)

            response = self.client.post(reverse("restore_world_folder", kwargs={"world_id": world.id}))

            self.assertEqual(response.status_code, 302)
            world.refresh_from_db()
            self.assertTrue(world.is_active)

    def test_superuser_cannot_restore_world_folder_when_path_is_missing(self):
        world = WorldFolder.objects.create(
            display_name="Missing World",
            source_path="/srv/worlds/missing",
            is_active=False,
        )
        self.client.force_login(self.superuser)

        response = self.client.post(reverse("restore_world_folder", kwargs={"world_id": world.id}))

        self.assertEqual(response.status_code, 302)
        world.refresh_from_db()
        self.assertFalse(world.is_active)

    def test_manual_world_folder_requires_level_dat(self):
        with TemporaryDirectory() as source_dir:
            self.client.force_login(self.superuser)

            response = self.client.post(
                reverse("create_world_folder"),
                {
                    "display_name": "Not a World",
                    "source_path": source_dir,
                    "is_active": "on",
                    "notes": "",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "This folder does not contain level.dat")
            self.assertFalse(WorldFolder.objects.exists())

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Project, ProjectVisibleWorld, WorldFolder


class ProjectManagementTests(TestCase):
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

    def test_manage_projects_requires_superuser(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("manage_projects"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_superuser_can_create_project_with_visible_worlds(self):
        world_a = WorldFolder.objects.create(
            display_name="World A",
            source_path="/srv/worlds/World_A",
        )
        world_b = WorldFolder.objects.create(
            display_name="World B",
            source_path="/srv/worlds/World_B",
        )
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("create_project"),
            {
                "name": "Survival Project",
                "description": "Main worlds",
                "owner_team": "Ops",
                "default_bluemap_profile": "",
                "visible_worlds": [world_a.id, world_b.id],
            },
        )

        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(name="Survival Project")
        self.assertEqual(project.description, "Main worlds")
        self.assertEqual(project.owner_team, "Ops")
        self.assertEqual(set(project.visible_worlds.all()), {world_a, world_b})

    def test_superuser_can_edit_project_visible_worlds(self):
        world_a = WorldFolder.objects.create(
            display_name="World A",
            source_path="/srv/worlds/World_A",
        )
        world_b = WorldFolder.objects.create(
            display_name="World B",
            source_path="/srv/worlds/World_B",
        )
        project = Project.objects.create(name="Survival Project")
        ProjectVisibleWorld.objects.create(project=project, world_folder=world_a)
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("edit_project", kwargs={"project_id": project.id}),
            {
                "name": "Renamed Project",
                "description": "Updated",
                "owner_team": "",
                "default_bluemap_profile": "",
                "visible_worlds": [world_b.id],
            },
        )

        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.name, "Renamed Project")
        self.assertEqual(list(project.visible_worlds.all()), [world_b])

    def test_project_form_tree_groups_worlds_by_parent_folder(self):
        with TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            grouped_world = source_root / "worlds_from_aternos" / "World_A"
            grouped_world.mkdir(parents=True)
            WorldFolder.objects.create(
                display_name="World A",
                source_path=str(grouped_world.resolve()),
            )
            self.client.force_login(self.superuser)

            with override_settings(SOURCE_WORLDS_DIR=source_root):
                response = self.client.get(reverse("create_project"))

            self.assertContains(response, "worlds_from_aternos")
            self.assertContains(response, "World A")
            self.assertContains(response, "data-world-folder-toggle")

    def test_inactive_worlds_are_not_available_for_project_visibility(self):
        active_world = WorldFolder.objects.create(
            display_name="Active World",
            source_path="/srv/worlds/Active",
            is_active=True,
        )
        inactive_world = WorldFolder.objects.create(
            display_name="Inactive World",
            source_path="/srv/worlds/Inactive",
            is_active=False,
        )
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("create_project"),
            {
                "name": "Survival Project",
                "description": "",
                "owner_team": "",
                "default_bluemap_profile": "",
                "visible_worlds": [active_world.id, inactive_world.id],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Project.objects.filter(name="Survival Project").exists())

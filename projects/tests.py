import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ProjectMembership
from .models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder


class ProjectAtlasRenderModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Survival Server")
        self.world = WorldFolder.objects.create(
            display_name="Overworld",
            source_path="/srv/minecraft/world",
        )

    def test_visible_world_does_not_create_atlas(self):
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.world)

        self.assertEqual(self.project.visible_worlds.count(), 1)
        self.assertEqual(self.project.atlases.count(), 0)

    def test_atlas_requires_visible_world(self):
        atlas = Atlas(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        with self.assertRaises(ValidationError):
            atlas.save()

    def test_render_effective_dimension_uses_custom_dimension(self):
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.world)
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            bluemap_map_id="overworld-spawn",
            display_name="Spawn Zoom",
            dimension=Render.Dimension.CUSTOM,
            custom_dimension="minecraft:overworld",
        )

        self.assertEqual(render.effective_dimension, "minecraft:overworld")


class ProjectSetupViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="password")
        self.user = User.objects.create_user(username="viewer", password="password")
        self.unassigned_user = User.objects.create_user(
            username="guest",
            password="password",
            email="guest@example.com",
        )
        self.project = Project.objects.create(name="Survival Server")
        self.world = WorldFolder.objects.create(
            display_name="Overworld",
            source_path="/srv/minecraft/world",
        )
        self.other_world = WorldFolder.objects.create(
            display_name="Archive",
            source_path="/srv/minecraft/archive",
        )
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.world)
        ProjectMembership.objects.create(
            user=self.admin,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_ADMINISTRATOR,
        )
        ProjectMembership.objects.create(
            user=self.user,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_USER,
        )

    def client_for(self, user):
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        return client

    def test_project_admin_can_create_atlas_from_visible_world(self):
        response = self.client_for(self.admin).post(
            reverse("create_atlas", kwargs={"slug": self.project.slug}),
            {
                "world_folder": self.world.id,
                "display_name": "Overworld",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.project.atlases.filter(display_name="Overworld").exists())

    def test_project_admin_cannot_create_atlas_from_invisible_world(self):
        response = self.client_for(self.admin).post(
            reverse("create_atlas", kwargs={"slug": self.project.slug}),
            {
                "world_folder": self.other_world.id,
                "display_name": "Archive",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.project.atlases.filter(display_name="Archive").exists())

    def test_project_admin_can_create_render_for_atlas(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.admin).post(
            reverse("create_render", kwargs={"atlas_id": atlas.id}),
            {
                "display_name": "HD 4K",
                "dimension": Render.Dimension.OVERWORLD,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.DAY,
                "sorting": 0,
            },
        )

        self.assertEqual(response.status_code, 302)
        render = atlas.renders.get(display_name="HD 4K")
        self.assertTrue(render.bluemap_map_id.startswith("render-"))
        uuid.UUID(render.bluemap_map_id.removeprefix("render-"))

    def test_project_user_cannot_create_atlas_or_render(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        atlas_response = self.client_for(self.user).post(
            reverse("create_atlas", kwargs={"slug": self.project.slug}),
            {
                "world_folder": self.world.id,
                "display_name": "Denied",
            },
        )
        render_response = self.client_for(self.user).post(
            reverse("create_render", kwargs={"atlas_id": atlas.id}),
            {
                "display_name": "Denied",
                "dimension": Render.Dimension.OVERWORLD,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.DAY,
                "sorting": 0,
            },
        )

        self.assertEqual(atlas_response.status_code, 403)
        self.assertEqual(render_response.status_code, 403)
        self.assertFalse(self.project.atlases.filter(display_name="Denied").exists())
        self.assertFalse(atlas.renders.filter(bluemap_map_id="denied").exists())

    def test_project_admin_can_add_existing_user_as_project_user_by_username(self):
        response = self.client_for(self.admin).post(
            reverse("add_project_user", kwargs={"slug": self.project.slug}),
            {
                "user_lookup": self.unassigned_user.username,
            },
        )

        self.assertEqual(response.status_code, 302)
        membership = ProjectMembership.objects.get(
            user=self.unassigned_user,
            project=self.project,
        )
        self.assertEqual(membership.role, ProjectMembership.Role.PROJECT_USER)

    def test_project_admin_can_add_existing_user_as_project_user_by_email(self):
        response = self.client_for(self.admin).post(
            reverse("add_project_user", kwargs={"slug": self.project.slug}),
            {
                "user_lookup": self.unassigned_user.email,
            },
        )

        self.assertEqual(response.status_code, 302)
        membership = ProjectMembership.objects.get(
            user=self.unassigned_user,
            project=self.project,
        )
        self.assertEqual(membership.role, ProjectMembership.Role.PROJECT_USER)

    def test_project_user_cannot_add_project_users(self):
        response = self.client_for(self.user).post(
            reverse("add_project_user", kwargs={"slug": self.project.slug}),
            {
                "user_lookup": self.unassigned_user.username,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProjectMembership.objects.filter(
                user=self.unassigned_user,
                project=self.project,
            ).exists()
        )

    def test_project_admin_can_remove_project_user_membership(self):
        membership = ProjectMembership.objects.create(
            user=self.unassigned_user,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_USER,
        )

        response = self.client_for(self.admin).post(
            reverse(
                "remove_project_membership",
                kwargs={"slug": self.project.slug, "membership_id": membership.id},
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectMembership.objects.filter(id=membership.id).exists())

    def test_project_admin_cannot_remove_project_administrator_membership(self):
        other_admin = User.objects.create_user(username="other-admin", password="password")
        membership = ProjectMembership.objects.create(
            user=other_admin,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_ADMINISTRATOR,
        )

        response = self.client_for(self.admin).post(
            reverse(
                "remove_project_membership",
                kwargs={"slug": self.project.slug, "membership_id": membership.id},
            ),
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProjectMembership.objects.filter(id=membership.id).exists())

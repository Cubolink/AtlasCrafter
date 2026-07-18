import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ProjectMembership
from renders.models import RenderJob
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

    def test_project_user_cannot_open_archived_project(self):
        self.project.is_active = False
        self.project.save(update_fields=["is_active"])

        response = self.client_for(self.user).get(
            reverse("project_detail", kwargs={"slug": self.project.slug}),
        )

        self.assertEqual(response.status_code, 403)

    def test_project_admin_cannot_manage_children_of_archived_project(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )
        self.project.is_active = False
        self.project.save(update_fields=["is_active"])

        edit_atlas_response = self.client_for(self.admin).get(
            reverse("edit_atlas", kwargs={"atlas_id": atlas.id}),
        )
        archive_atlas_response = self.client_for(self.admin).post(
            reverse("archive_atlas", kwargs={"atlas_id": atlas.id}),
        )
        edit_render_response = self.client_for(self.admin).get(
            reverse("edit_render", kwargs={"render_id": render.id}),
        )
        archive_render_response = self.client_for(self.admin).post(
            reverse("archive_render", kwargs={"render_id": render.id}),
        )

        self.assertEqual(edit_atlas_response.status_code, 404)
        self.assertEqual(archive_atlas_response.status_code, 404)
        self.assertEqual(edit_render_response.status_code, 404)
        self.assertEqual(archive_render_response.status_code, 404)

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

    def test_project_user_sees_project_section_tabs(self):
        response = self.client_for(self.user).get(
            reverse("project_detail", kwargs={"slug": self.project.slug}),
        )

        self.assertContains(response, reverse("project_members", kwargs={"slug": self.project.slug}))
        self.assertContains(response, reverse("project_worlds", kwargs={"slug": self.project.slug}))

    def test_project_user_can_view_members_without_manage_actions(self):
        response = self.client_for(self.user).get(
            reverse("project_members", kwargs={"slug": self.project.slug}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin.username)
        self.assertContains(response, self.user.username)
        self.assertNotContains(response, "Add Project User")
        self.assertNotContains(response, "Remove")

    def test_project_user_can_view_only_worlds_used_by_atlases(self):
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.other_world)
        Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.user).get(
            reverse("project_worlds", kwargs={"slug": self.project.slug}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Atlas World Folders")
        self.assertContains(response, self.world.display_name)
        self.assertNotContains(response, self.other_world.display_name)

    def test_project_admin_can_edit_atlas(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.admin).post(
            reverse("edit_atlas", kwargs={"atlas_id": atlas.id}),
            {
                "display_name": "Renamed Atlas",
                "notes": "Updated notes",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        atlas.refresh_from_db()
        self.assertEqual(atlas.display_name, "Renamed Atlas")
        self.assertEqual(atlas.notes, "Updated notes")

    def test_project_admin_can_archive_atlas(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.admin).post(
            reverse("archive_atlas", kwargs={"atlas_id": atlas.id}),
        )

        self.assertEqual(response.status_code, 302)
        atlas.refresh_from_db()
        self.assertFalse(atlas.is_active)

    def test_project_admin_can_view_and_restore_archived_atlases(self):
        active_atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Current Nether",
        )
        archived_atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Old Overworld",
            is_active=False,
        )

        detail_response = self.client_for(self.admin).get(
            reverse("project_detail", kwargs={"slug": self.project.slug}),
        )
        archive_response = self.client_for(self.admin).get(
            reverse("archived_atlases", kwargs={"slug": self.project.slug}),
        )
        restore_response = self.client_for(self.admin).post(
            reverse("restore_atlas", kwargs={"atlas_id": archived_atlas.id}),
        )

        self.assertContains(detail_response, reverse("archived_atlases", kwargs={"slug": self.project.slug}))
        self.assertContains(archive_response, archived_atlas.display_name)
        self.assertNotContains(archive_response, active_atlas.display_name)
        self.assertEqual(restore_response.status_code, 302)
        archived_atlas.refresh_from_db()
        self.assertTrue(archived_atlas.is_active)

    def test_project_user_cannot_view_archived_atlases(self):
        response = self.client_for(self.user).get(
            reverse("archived_atlases", kwargs={"slug": self.project.slug}),
        )

        self.assertEqual(response.status_code, 403)

    def test_project_admin_cannot_archive_atlas_with_active_render_job(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )
        RenderJob.objects.create(render=render, status=RenderJob.Status.QUEUED)

        response = self.client_for(self.admin).post(
            reverse("archive_atlas", kwargs={"atlas_id": atlas.id}),
        )

        self.assertEqual(response.status_code, 302)
        atlas.refresh_from_db()
        self.assertTrue(atlas.is_active)

    def test_project_admin_can_edit_render_without_changing_bluemap_id(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            bluemap_map_id="stable-render-id",
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )

        response = self.client_for(self.admin).post(
            reverse("edit_render", kwargs={"render_id": render.id}),
            {
                "display_name": "Renamed Render",
                "dimension": Render.Dimension.NETHER,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.NIGHT,
                "sorting": 10,
                "is_enabled": "on",
                "storage_profile": "file",
                "sky_color": "#112233",
                "void_color": "#445566",
                "sky_light": "0.75",
                "ambient_light": "0.25",
                "remove_caves_below_y": 42,
                "cave_detection_ocean_floor": -3,
                "cave_detection_uses_block_light": "on",
                "min_inhabited_time": 1200,
                "render_edges": "on",
                "edge_light_strength": 12,
                "enable_perspective_view": "on",
                "enable_flat_view": "on",
                "enable_free_flight_view": "on",
                "enable_hires": "on",
                "ignore_missing_light_data": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        render.refresh_from_db()
        self.assertEqual(render.display_name, "Renamed Render")
        self.assertEqual(render.dimension, Render.Dimension.NETHER)
        self.assertEqual(render.perspective_preset, Render.PerspectivePreset.NIGHT)
        self.assertEqual(render.sorting, 10)
        self.assertEqual(render.bluemap_map_id, "stable-render-id")
        self.assertEqual(render.sky_color, "#112233")
        self.assertTrue(render.cave_detection_uses_block_light)
        self.assertEqual(render.edge_light_strength, 12)
        self.assertTrue(render.ignore_missing_light_data)

    def test_project_admin_can_archive_render(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )

        response = self.client_for(self.admin).post(
            reverse("archive_render", kwargs={"render_id": render.id}),
        )

        self.assertEqual(response.status_code, 302)
        render.refresh_from_db()
        self.assertFalse(render.is_enabled)

    def test_project_admin_can_view_and_restore_archived_renders(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        active_render = Render.objects.create(
            atlas=atlas,
            display_name="Current HD",
            dimension=Render.Dimension.OVERWORLD,
            is_enabled=True,
        )
        archived_render = Render.objects.create(
            atlas=atlas,
            display_name="Old Standard",
            dimension=Render.Dimension.OVERWORLD,
            is_enabled=False,
        )

        detail_response = self.client_for(self.admin).get(
            reverse("atlas_detail", kwargs={"atlas_id": atlas.id}),
        )
        archive_response = self.client_for(self.admin).get(
            reverse("archived_renders", kwargs={"atlas_id": atlas.id}),
        )
        restore_response = self.client_for(self.admin).post(
            reverse("restore_render", kwargs={"render_id": archived_render.id}),
        )

        self.assertContains(detail_response, reverse("archived_renders", kwargs={"atlas_id": atlas.id}))
        self.assertContains(archive_response, archived_render.display_name)
        self.assertNotContains(archive_response, active_render.display_name)
        self.assertEqual(restore_response.status_code, 302)
        archived_render.refresh_from_db()
        self.assertTrue(archived_render.is_enabled)

    def test_project_user_cannot_view_archived_renders(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.user).get(
            reverse("archived_renders", kwargs={"atlas_id": atlas.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_project_admin_cannot_archive_render_with_active_job(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )
        RenderJob.objects.create(render=render, status=RenderJob.Status.RUNNING)

        response = self.client_for(self.admin).post(
            reverse("archive_render", kwargs={"render_id": render.id}),
        )

        self.assertEqual(response.status_code, 302)
        render.refresh_from_db()
        self.assertTrue(render.is_enabled)

    def test_project_user_cannot_edit_or_archive_atlas_or_render(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        render = Render.objects.create(
            atlas=atlas,
            display_name="Standard",
            dimension=Render.Dimension.OVERWORLD,
        )

        edit_atlas_response = self.client_for(self.user).post(
            reverse("edit_atlas", kwargs={"atlas_id": atlas.id}),
            {"display_name": "Denied", "notes": "", "is_active": "on"},
        )
        archive_atlas_response = self.client_for(self.user).post(
            reverse("archive_atlas", kwargs={"atlas_id": atlas.id}),
        )
        edit_render_response = self.client_for(self.user).post(
            reverse("edit_render", kwargs={"render_id": render.id}),
            {
                "display_name": "Denied",
                "dimension": Render.Dimension.OVERWORLD,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.DAY,
                "sorting": 0,
                "is_enabled": "on",
                "storage_profile": "",
                "sky_color": "#7dabff",
                "void_color": "#000000",
                "sky_light": "1.00",
                "ambient_light": "0.00",
                "remove_caves_below_y": 55,
                "cave_detection_ocean_floor": -5,
                "min_inhabited_time": 0,
                "render_edges": "on",
                "edge_light_strength": 8,
                "enable_perspective_view": "on",
                "enable_flat_view": "on",
                "enable_free_flight_view": "on",
                "enable_hires": "on",
            },
        )
        archive_render_response = self.client_for(self.user).post(
            reverse("archive_render", kwargs={"render_id": render.id}),
        )

        self.assertEqual(edit_atlas_response.status_code, 403)
        self.assertEqual(archive_atlas_response.status_code, 403)
        self.assertEqual(edit_render_response.status_code, 403)
        self.assertEqual(archive_render_response.status_code, 403)
        atlas.refresh_from_db()
        render.refresh_from_db()
        self.assertEqual(atlas.display_name, "Overworld")
        self.assertEqual(render.display_name, "Standard")

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

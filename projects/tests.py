import json
import uuid
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import ProjectMembership
from bluemap_configs.models import BlueMapProfile
from renders.models import RenderJob
from .markers import build_marker_snapshot, format_marker_sets, safe_html_marker
from .models import Atlas, Marker, MarkerSet, Project, ProjectVisibleWorld, Render, WorldFolder


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

    def test_project_admin_create_render_applies_preset_defaults(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.admin).post(
            reverse("create_render", kwargs={"atlas_id": atlas.id}),
            {
                "display_name": "Night Map",
                "dimension": Render.Dimension.OVERWORLD,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.NIGHT,
                "sorting": 0,
            },
        )

        self.assertEqual(response.status_code, 302)
        render = atlas.renders.get(display_name="Night Map")
        self.assertEqual(render.sky_color, "#1d2b53")
        self.assertEqual(render.sky_light, Decimal("0.25"))
        self.assertEqual(render.ambient_light, Decimal("0.05"))
        self.assertTrue(render.enable_perspective_view)
        self.assertTrue(render.enable_flat_view)

    def test_project_admin_create_render_custom_preset_keeps_model_defaults(self):
        atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )

        response = self.client_for(self.admin).post(
            reverse("create_render", kwargs={"atlas_id": atlas.id}),
            {
                "display_name": "Manual Map",
                "dimension": Render.Dimension.OVERWORLD,
                "custom_dimension": "",
                "perspective_preset": Render.PerspectivePreset.CUSTOM,
                "sorting": 0,
            },
        )

        self.assertEqual(response.status_code, 302)
        render = atlas.renders.get(display_name="Manual Map")
        self.assertEqual(render.sky_color, "#7dabff")
        self.assertEqual(render.sky_light, Decimal("1.00"))
        self.assertEqual(render.ambient_light, Decimal("0.00"))

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
                "start_x": 10,
                "start_y": 80,
                "start_z": -20,
                "render_mask_type": "box",
                "render_mask_subtract": "",
                "render_mask_min_x": -100,
                "render_mask_max_x": 100,
                "render_mask_min_y": "",
                "render_mask_max_y": "",
                "render_mask_min_z": -200,
                "render_mask_max_z": 200,
                "render_mask_center_x": "",
                "render_mask_center_z": "",
                "render_mask_radius": "",
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
        self.assertEqual(render.start_position, {"x": 10, "y": 80, "z": -20})
        self.assertEqual(
            render.render_mask,
            [
                {
                    "type": "box",
                    "min-x": -100,
                    "max-x": 100,
                    "min-z": -200,
                    "max-z": 200,
                },
            ],
        )
        self.assertTrue(render.cave_detection_uses_block_light)
        self.assertEqual(render.edge_light_strength, 12)
        self.assertTrue(render.ignore_missing_light_data)

    def test_edit_render_shows_read_only_raw_config_tab(self):
        BlueMapProfile.objects.create(name="Default", slug="default")
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

        response = self.client_for(self.admin).get(
            reverse("edit_render", kwargs={"render_id": render.id}),
        )

        self.assertContains(response, "Friendly Editor")
        self.assertContains(response, "Raw Config")
        self.assertContains(response, "Raw config editing is coming next")
        self.assertContains(response, "readonly")
        self.assertContains(response, "name:")
        self.assertContains(response, "Standard")

    def test_edit_render_uses_enhanced_form_controls(self):
        BlueMapProfile.objects.create(name="Default", slug="default")
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

        response = self.client_for(self.admin).get(
            reverse("edit_render", kwargs={"render_id": render.id}),
        )

        self.assertContains(response, 'type="color"')
        self.assertContains(response, 'type="range"')
        self.assertContains(response, "data-range-control")
        self.assertContains(response, 'class="toggle toggle-primary"')
        self.assertContains(response, "collapse collapse-arrow")
        self.assertContains(response, "Advanced Settings")
        self.assertContains(response, "data-render-preset-form")
        self.assertContains(response, "data-apply-render-preset")
        self.assertContains(response, "Apply Preset Settings")
        self.assertContains(response, "Start Position")
        self.assertContains(response, "Render Mask")
        self.assertContains(response, "data-render-mask-type")
        self.assertNotContains(response, 'name="marker_sets"')
        self.assertNotContains(response, "Raw BlueMap marker-sets HOCON")
        self.assertContains(response, "Minecraft Resources")
        self.assertContains(response, "Use world or server default")
        self.assertContains(response, "Vanilla resources only")
        self.assertContains(response, "minecraft_version_override")

    def test_render_forms_hide_custom_dimension_until_custom_dimension_selected(self):
        BlueMapProfile.objects.create(name="Default", slug="default")
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

        edit_response = self.client_for(self.admin).get(
            reverse("edit_render", kwargs={"render_id": render.id}),
        )
        atlas_response = self.client_for(self.admin).get(
            reverse("atlas_detail", kwargs={"atlas_id": atlas.id}),
        )

        self.assertContains(edit_response, "data-dimension-select")
        self.assertContains(edit_response, "data-custom-dimension-wrapper")
        self.assertContains(edit_response, "mod/datapack dimension key")
        self.assertContains(edit_response, "Preset defaults for the advanced render fields")
        self.assertContains(atlas_response, "data-dimension-select")
        self.assertContains(atlas_response, "data-custom-dimension-wrapper")
        self.assertContains(atlas_response, "data-render-preset-summary")

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

    def test_atlas_detail_shows_latest_render_job_summary(self):
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
        old_job = RenderJob.objects.create(render=render, status=RenderJob.Status.FAILED)
        latest_job = RenderJob.objects.create(render=render, status=RenderJob.Status.SUCCEEDED)

        response = self.client_for(self.admin).get(
            reverse("atlas_detail", kwargs={"atlas_id": atlas.id}),
        )

        self.assertContains(response, f"#{latest_job.id}")
        self.assertContains(response, latest_job.get_status_display())
        self.assertNotContains(response, f"#{old_job.id}")

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


class RenderMarkerManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="marker-admin", password="password")
        self.viewer = User.objects.create_user(username="marker-viewer", password="password")
        self.project = Project.objects.create(name="Marker Project")
        self.profile = BlueMapProfile.objects.create(
            name="Marker Profile",
            slug="marker-profile",
        )
        self.project.default_bluemap_profile = self.profile
        self.project.save(update_fields=["default_bluemap_profile"])
        self.world = WorldFolder.objects.create(
            display_name="Marker World",
            source_path="/srv/minecraft/marker-world",
        )
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.world)
        self.atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Marker Atlas",
        )
        self.render = Render.objects.create(
            atlas=self.atlas,
            display_name="Marker Render",
            dimension=Render.Dimension.OVERWORLD,
        )
        ProjectMembership.objects.create(
            user=self.admin,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_ADMINISTRATOR,
        )
        ProjectMembership.objects.create(
            user=self.viewer,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_USER,
        )

    def client_for(self, user):
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        return client

    def async_headers(self):
        return {
            "HTTP_ACCEPT": "application/json",
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
        }

    def test_project_admin_can_create_marker_set_and_poi(self):
        admin_client = self.client_for(self.admin)
        set_response = admin_client.post(
            reverse("create_marker_set", kwargs={"render_id": self.render.id}),
            {
                "label": "Landmarks",
                "sorting": 1,
                "toggleable": "on",
                "default_hidden": "",
            },
        )

        self.assertRedirects(
            set_response,
            reverse("render_markers", kwargs={"render_id": self.render.id}),
        )
        marker_set = MarkerSet.objects.get(render=self.render)
        marker_response = admin_client.post(
            reverse("create_marker", kwargs={"marker_set_id": marker_set.id}),
            {
                "label": "Spawn",
                "detail": "Welcome <script>alert(1)</script>",
                "position_x": "10.5",
                "position_y": "80",
                "position_z": "-20",
                "sorting": 0,
                "listed": "on",
                "min_distance": "",
                "max_distance": "5000",
            },
        )

        self.assertRedirects(
            marker_response,
            reverse("render_markers", kwargs={"render_id": self.render.id}),
        )
        marker = Marker.objects.get(marker_set=marker_set)
        self.assertEqual(marker.label, "Spawn")
        self.assertIn("<script>", marker.detail)
        page = admin_client.get(reverse("render_markers", kwargs={"render_id": self.render.id}))
        self.assertContains(page, "Landmarks")
        self.assertContains(page, "Spawn")
        self.assertContains(page, "js/marker_workspace.js")
        self.assertContains(page, "data-marker-editor-link")
        self.assertNotContains(page, 'name="marker_sets"')

    def test_project_user_cannot_manage_markers(self):
        response = self.client_for(self.viewer).get(
            reverse("render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertEqual(response.status_code, 403)

    def test_project_admin_can_queue_marker_publication_without_world_on_disk(self):
        response = self.client_for(self.admin).post(
            reverse("publish_render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertRedirects(
            response,
            reverse("render_markers", kwargs={"render_id": self.render.id}),
        )
        job = RenderJob.objects.get(render=self.render)
        self.assertEqual(job.operation, RenderJob.Operation.MARKERS)
        self.assertEqual(job.status, RenderJob.Status.QUEUED)

    def test_marker_manager_marks_new_and_modified_markers(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        published_marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )
        self.render.published_marker_snapshot = build_marker_snapshot(self.render)
        self.render.save(update_fields=["published_marker_snapshot"])
        published_marker.label = "Main Spawn"
        published_marker.save(update_fields=["label", "updated_at"])
        Marker.objects.create(
            marker_set=marker_set,
            label="Village",
            position_x=100,
            position_y=70,
            position_z=-100,
        )

        response = self.client_for(self.admin).get(
            reverse("render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertContains(response, "Unpublished marker changes")
        self.assertContains(response, "marker-publication-rail-warning")
        self.assertContains(response, "Modified")
        self.assertContains(response, "New")
        self.assertContains(response, "Published Map")

    def test_marker_manager_keeps_deleted_marker_as_pending_removal(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Old Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )
        self.render.published_marker_snapshot = build_marker_snapshot(self.render)
        self.render.save(update_fields=["published_marker_snapshot"])
        marker.delete()

        response = self.client_for(self.admin).get(
            reverse("render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertContains(response, "Old Spawn")
        self.assertContains(response, "Pending removal")
        self.assertContains(response, "Still visible on the published map")

    def test_marker_manager_explains_unknown_publication_baseline(self):
        MarkerSet.objects.create(render=self.render, label="Landmarks")

        response = self.client_for(self.admin).get(
            reverse("render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertContains(response, "Publication tracking has not established a baseline")
        self.assertContains(response, "marker-publication-rail-neutral")
        self.assertContains(response, "Not tracked yet")

    def test_marker_manager_uses_compact_status_for_synchronized_markers(self):
        MarkerSet.objects.create(render=self.render, label="Landmarks")
        self.render.published_marker_snapshot = build_marker_snapshot(self.render)
        self.render.save(update_fields=["published_marker_snapshot"])

        response = self.client_for(self.admin).get(
            reverse("render_markers", kwargs={"render_id": self.render.id})
        )

        self.assertContains(response, "In sync")
        self.assertContains(response, "marker-publication-rail-success")
        self.assertNotContains(response, "alert alert-success")

    def test_marker_manager_embeds_only_available_published_output(self):
        with TemporaryDirectory() as webroot_dir:
            webroot = Path(webroot_dir)
            map_dir = webroot / "maps" / self.render.bluemap_map_id
            map_dir.mkdir(parents=True)
            (webroot / "index.html").write_text("<html>BlueMap</html>", encoding="utf-8")
            (map_dir / "settings.json").write_text("{}", encoding="utf-8")

            with override_settings(BLUEMAP_WEBROOT_DIR=webroot):
                response = self.client_for(self.admin).get(
                    reverse("render_markers", kwargs={"render_id": self.render.id})
                )

        self.assertContains(response, "<iframe", html=False)
        self.assertContains(
            response,
            reverse(
                "protected_render_asset",
                kwargs={"render_id": self.render.id, "asset_path": "index.html"},
            ),
        )

    def test_marker_manager_opens_existing_marker_in_quick_editor(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=10,
            position_y=64,
            position_z=-20,
        )

        response = self.client_for(self.admin).get(
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}?edit={marker.id}"
        )

        self.assertContains(response, "Quick edit")
        self.assertContains(response, 'name="editor_action" value="edit"', html=False)
        self.assertContains(response, 'value="Spawn"', html=False)
        self.assertContains(response, ">10, 64, -20</code>", html=False)
        self.assertContains(response, 'name="position_x" value="10"', html=False)
        self.assertContains(response, 'name="position_x" value="10" step="any"', html=False)
        self.assertNotContains(response, "10.000, 64.000, -20.000")
        self.assertContains(response, "More options")
        self.assertContains(response, "Saved changes remain drafts")
        self.assertContains(response, 'name="submit_action" value="save"', html=False)
        self.assertContains(response, "data-marker-save-button")
        self.assertNotContains(response, 'value="save_publish"', html=False)
        self.assertContains(response, "Publish Markers")

    def test_marker_manager_offers_safe_styled_label_editor(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Labels")

        response = self.client_for(self.admin).get(
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}"
            f"?create={marker_set.id}&type=html"
        )

        self.assertContains(response, "Styled label")
        self.assertContains(response, 'name="marker_type" value="html"', html=False)
        self.assertContains(response, "data-html-marker-preview")
        self.assertContains(response, 'type="color"', html=False)
        self.assertContains(response, "No HTML or CSS is accepted")
        self.assertNotContains(response, 'name="detail"', html=False)
        self.assertNotContains(response, 'name="html"', html=False)
        self.assertNotContains(response, 'name="css"', html=False)

    def test_admin_can_create_styled_label_from_quick_editor(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Labels")

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "create",
                "marker_set_id": marker_set.id,
                "marker_type": "html",
                "label": "Market",
                "position_x": "20.5",
                "position_y": "70",
                "position_z": "-12",
                "html_variant": "sign",
                "html_size": "large",
                "html_symbol": "star",
                "html_text_color": "#fff4cc",
                "html_background_color": "#7c3aed",
                "sorting": "2",
                "listed": "on",
                "min_distance": "",
                "max_distance": "5000",
                "submit_action": "save",
            },
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 200)
        marker = Marker.objects.get(marker_set=marker_set)
        self.assertEqual(marker.marker_type, Marker.Type.HTML)
        self.assertEqual(marker.html_variant, Marker.HTMLVariant.SIGN)
        self.assertEqual(marker.html_size, Marker.HTMLSize.LARGE)
        self.assertEqual(marker.html_symbol, Marker.HTMLSymbol.STAR)
        self.assertEqual(marker.html_background_color, "#7c3aed")
        self.assertEqual(response.json()["notice"]["presentation"], "inline-save")

        marker_config = format_marker_sets(self.render)
        self.assertIn('type: "html"', marker_config)
        self.assertIn("font-size:22px", marker_config)
        self.assertIn("background:#7c3aed", marker_config)
        self.assertIn("★", marker_config)
        self.assertIn("anchor: { x: 0, y: 0 }", marker_config)

    def test_admin_can_create_line_area_and_volume_markers(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Regions")
        common = {
            "editor_action": "create",
            "marker_set_id": marker_set.id,
            "detail": "Safe description",
            "line_width": "4",
            "line_color": "#ef4444",
            "line_opacity": "0.75",
            "depth_test": "on",
            "link": "https://example.com/guide",
            "new_tab": "on",
            "sorting": "0",
            "listed": "on",
            "min_distance": "",
            "max_distance": "5000",
            "submit_action": "save",
        }
        cases = [
            (
                Marker.Type.LINE,
                "Road",
                [
                    {"x": "0", "y": "64", "z": "0"},
                    {"x": "10", "y": "70", "z": "20"},
                ],
                {},
                (Decimal("5"), Decimal("67"), Decimal("10")),
            ),
            (
                Marker.Type.SHAPE,
                "Town",
                [
                    {"x": "0", "z": "0"},
                    {"x": "10", "z": "0"},
                    {"x": "10", "z": "10"},
                    {"x": "0", "z": "10"},
                ],
                {"position_y": "70", "fill_color": "#22c55e", "fill_opacity": "0.25"},
                (Decimal("5"), Decimal("70"), Decimal("5")),
            ),
            (
                Marker.Type.EXTRUDE,
                "Protected volume",
                [
                    {"x": "0", "z": "0"},
                    {"x": "4", "z": "0"},
                    {"x": "4", "z": "8"},
                    {"x": "0", "z": "8"},
                ],
                {
                    "shape_min_y": "60",
                    "shape_max_y": "80",
                    "fill_color": "#3b82f6",
                    "fill_opacity": "0.4",
                },
                (Decimal("2"), Decimal("70"), Decimal("4")),
            ),
        ]

        for marker_type, label, vertices, extra, expected_position in cases:
            with self.subTest(marker_type=marker_type):
                response = self.client_for(self.admin).post(
                    reverse("render_markers", kwargs={"render_id": self.render.id}),
                    {
                        **common,
                        **extra,
                        "marker_type": marker_type,
                        "label": label,
                        "vertices": json.dumps(vertices),
                    },
                    **self.async_headers(),
                )
                self.assertEqual(response.status_code, 200)
                marker = Marker.objects.get(marker_set=marker_set, marker_type=marker_type)
                self.assertEqual(
                    (marker.position_x, marker.position_y, marker.position_z),
                    expected_position,
                )
                self.assertEqual(marker.geometry, vertices)

        marker_config = format_marker_sets(self.render)
        self.assertIn('type: "line"', marker_config)
        self.assertIn("line: [", marker_config)
        self.assertIn("{ x: 10, y: 70, z: 20 }", marker_config)
        self.assertIn('type: "shape"', marker_config)
        self.assertIn("shape-y: 70", marker_config)
        self.assertIn('type: "extrude"', marker_config)
        self.assertIn("shape-min-y: 60", marker_config)
        self.assertIn("shape-max-y: 80", marker_config)
        self.assertIn("line-color: { r: 239, g: 68, b: 68, a: 0.75 }", marker_config)
        self.assertIn('link: "https://example.com/guide"', marker_config)
        self.assertIn("new-tab: true", marker_config)

    def test_geometry_editor_uses_safe_coordinate_rows_without_raw_configuration(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Regions")

        response = self.client_for(self.admin).get(
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}"
            f"?create={marker_set.id}&type=shape"
        )

        self.assertContains(response, "data-geometry-editor")
        self.assertContains(response, 'name="vertices"', html=False)
        self.assertContains(response, 'type="hidden"', html=False)
        self.assertContains(response, 'type="color"', count=2, html=False)
        self.assertNotContains(response, 'type="text" name="line_color"', html=False)
        self.assertNotContains(response, 'type="text" name="fill_color"', html=False)
        self.assertContains(response, "Add corners in order around the boundary")
        self.assertNotContains(response, 'textarea name="vertices"', html=False)
        self.assertNotContains(response, "Raw HOCON")

    def test_geometry_marker_rejects_incomplete_vertices_and_unsafe_links(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Regions")
        base_payload = {
            "editor_action": "create",
            "marker_set_id": marker_set.id,
            "marker_type": Marker.Type.SHAPE,
            "label": "Unsafe area",
            "detail": "",
            "position_y": "64",
            "vertices": json.dumps([{"x": "0", "z": "0"}, {"x": "1", "z": "1"}]),
            "line_width": "3",
            "line_color": "#ef4444",
            "line_opacity": "1",
            "fill_color": "#ef4444",
            "fill_opacity": "0.25",
            "link": "javascript:alert(1)",
            "sorting": "0",
            "listed": "on",
            "min_distance": "",
            "max_distance": "",
            "submit_action": "save",
        }

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            base_payload,
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 422)
        html = response.json()["marker_editor_html"]
        self.assertIn("Add at least 3 vertices", html)
        self.assertIn("Enter a valid URL", html)
        self.assertFalse(Marker.objects.filter(marker_set=marker_set).exists())

    def test_styled_label_generated_html_escapes_user_text(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Labels")
        marker = Marker.objects.create(
            marker_set=marker_set,
            marker_type=Marker.Type.HTML,
            label='<img src=x onerror="alert(1)">',
            position_x=0,
            position_y=64,
            position_z=0,
            html_variant=Marker.HTMLVariant.BADGE,
            html_symbol=Marker.HTMLSymbol.PIN,
        )
        marker_data = build_marker_snapshot(self.render)["sets"][marker_set.bluemap_id][
            "markers"
        ][marker.bluemap_id]

        generated_html = safe_html_marker(marker_data)

        self.assertNotIn("<img", generated_html)
        self.assertIn("&lt;img", generated_html)
        self.assertIn("&quot;alert(1)&quot;", generated_html)
        self.assertTrue(generated_html.startswith('<div style="'))

    def test_styled_label_rejects_unlisted_styles_and_invalid_colors(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Labels")

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "create",
                "marker_set_id": marker_set.id,
                "marker_type": "html",
                "label": "Unsafe",
                "position_x": "0",
                "position_y": "64",
                "position_z": "0",
                "html_variant": "custom-css",
                "html_size": "medium",
                "html_symbol": "pin",
                "html_text_color": "#ffffff",
                "html_background_color": "#fff;position:fixed",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(Marker.objects.filter(marker_set=marker_set).exists())
        self.assertIn("Select a valid choice", response.json()["marker_editor_html"])

    def test_standalone_marker_forms_only_offer_save(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )

        for url in [
            reverse("edit_marker", kwargs={"marker_id": marker.id}),
            reverse("edit_marker_set", kwargs={"marker_set_id": marker_set.id}),
        ]:
            with self.subTest(url=url):
                response = self.client_for(self.admin).get(url)
                self.assertContains(response, 'name="submit_action" value="save"', html=False)
                self.assertNotContains(response, 'value="save_publish"', html=False)

    def test_admin_can_create_marker_from_quick_editor(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "create",
                "marker_set_id": marker_set.id,
                "label": "Village",
                "detail": "Trading hall",
                "position_x": "120",
                "position_y": "70",
                "position_z": "-350",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
        )

        marker = Marker.objects.get(marker_set=marker_set, label="Village")
        self.assertEqual(marker.position_z, Decimal("-350"))
        self.assertEqual(
            response.headers["Location"],
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}?edit={marker.id}#marker-editor",
        )
        self.assertFalse(RenderJob.objects.filter(render=self.render).exists())

    def test_admin_can_update_marker_coordinates_from_quick_editor(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "edit",
                "marker_id": marker.id,
                "label": "Main Spawn",
                "detail": "",
                "position_x": "4.5",
                "position_y": "65",
                "position_z": "-8.25",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        marker.refresh_from_db()
        self.assertEqual(marker.label, "Main Spawn")
        self.assertEqual(marker.position_x, Decimal("4.5"))
        self.assertEqual(marker.position_z, Decimal("-8.25"))

    def test_quick_editor_validation_errors_stay_in_marker_workspace(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "create",
                "marker_set_id": marker_set.id,
                "label": "",
                "detail": "",
                "position_x": "not-a-coordinate",
                "position_y": "64",
                "position_z": "0",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertContains(response, "Enter a number")
        self.assertContains(response, "Published Map")
        self.assertFalse(Marker.objects.filter(marker_set=marker_set).exists())

    def test_async_marker_selection_returns_workspace_fragments(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )

        response = self.client_for(self.admin).get(
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}?edit={marker.id}",
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('id="marker-browser"', payload["marker_browser_html"])
        self.assertIn('id="marker-editor"', payload["marker_editor_html"])
        self.assertIn("Quick edit", payload["marker_editor_html"])
        self.assertIn('value="Spawn"', payload["marker_editor_html"])
        self.assertEqual(
            payload["editor_url"],
            f"{reverse('render_markers', kwargs={'render_id': self.render.id})}?edit={marker.id}#marker-editor",
        )

    def test_async_quick_edit_updates_marker_without_redirect(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Spawn",
            position_x=0,
            position_y=64,
            position_z=0,
        )

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "edit",
                "marker_id": marker.id,
                "label": "Main Spawn",
                "detail": "",
                "position_x": "2.5",
                "position_y": "65",
                "position_z": "-4",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 200)
        marker.refresh_from_db()
        self.assertEqual(marker.label, "Main Spawn")
        self.assertEqual(marker.position_x, Decimal("2.5"))
        payload = response.json()
        self.assertIn("Main Spawn", payload["marker_browser_html"])
        self.assertEqual(payload["notice"]["level"], "success")
        self.assertEqual(payload["notice"]["presentation"], "inline-save")
        self.assertIsNone(payload["active_job_id"])

    def test_async_quick_edit_returns_validation_fragments(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")

        response = self.client_for(self.admin).post(
            reverse("render_markers", kwargs={"render_id": self.render.id}),
            {
                "editor_action": "create",
                "marker_set_id": marker_set.id,
                "label": "",
                "detail": "",
                "position_x": "invalid",
                "position_y": "64",
                "position_z": "0",
                "sorting": "0",
                "listed": "on",
                "min_distance": "",
                "max_distance": "",
                "submit_action": "save",
            },
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIn("This field is required", payload["marker_editor_html"])
        self.assertIn("Enter a number", payload["marker_editor_html"])
        self.assertEqual(payload["notice"]["level"], "error")

    def test_async_marker_delete_refreshes_browser_fragment(self):
        marker_set = MarkerSet.objects.create(render=self.render, label="Landmarks")
        marker = Marker.objects.create(
            marker_set=marker_set,
            label="Temporary Point",
            position_x=0,
            position_y=64,
            position_z=0,
        )

        response = self.client_for(self.admin).post(
            reverse("delete_marker", kwargs={"marker_id": marker.id}),
            {},
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Marker.objects.filter(id=marker.id).exists())
        payload = response.json()
        self.assertNotIn("Temporary Point", payload["marker_browser_html"])
        self.assertIn("Marker 'Temporary Point' deleted", payload["notice"]["message"])

    def test_async_publish_queues_job_and_returns_polling_state(self):
        response = self.client_for(self.admin).post(
            reverse("publish_render_markers", kwargs={"render_id": self.render.id}),
            {},
            **self.async_headers(),
        )

        self.assertEqual(response.status_code, 200)
        job = RenderJob.objects.get(render=self.render)
        payload = response.json()
        self.assertEqual(payload["active_job_id"], job.id)
        self.assertIn("Job in progress", payload["publish_action_html"])
        self.assertIn(f'href="{reverse("render_job_detail", kwargs={"job_id": job.id})}"', payload["publication_status_html"])
        self.assertEqual(payload["notice"]["level"], "success")

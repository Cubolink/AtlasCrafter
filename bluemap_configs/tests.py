from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from .forms import DEFAULT_PROFILE_COMMAND_TEMPLATE
from .models import BlueMapProfile, BlueMapRenderConfig


User = get_user_model()


class BlueMapRenderConfigTests(TestCase):
    def test_generate_content_uses_render_context(self):
        render = self.create_render()
        profile = BlueMapProfile.objects.create(
            name="Default",
            slug="default",
            config_template='id="{map_id}" world="{world_path}" dimension="{dimension}"',
        )
        render_config = BlueMapRenderConfig.objects.create(render=render, profile=profile)

        content = render_config.generate_content()

        self.assertIn("# Project: Survival Server", content)
        self.assertIn("# Atlas: Overworld", content)
        self.assertIn("# Render: HD 4K", content)
        self.assertIn('id="overworld-hd"', content)
        self.assertIn('world="/srv/minecraft/world"', content)
        self.assertIn('dimension="minecraft:overworld"', content)

    def test_default_template_generates_content(self):
        render = self.create_render()
        render.sky_color = "#112233"
        render.void_color = "#445566"
        render.sky_light = Decimal("0.75")
        render.ambient_light = Decimal("0.25")
        render.remove_caves_below_y = 42
        render.cave_detection_ocean_floor = -3
        render.cave_detection_uses_block_light = True
        render.min_inhabited_time = 1200
        render.render_edges = False
        render.edge_light_strength = 12
        render.enable_perspective_view = False
        render.enable_flat_view = True
        render.enable_free_flight_view = False
        render.enable_hires = True
        render.storage_profile = "file"
        render.ignore_missing_light_data = True
        render.start_position = {"x": 10, "y": 80, "z": -20}
        render.render_mask = [
            {
                "type": "box",
                "subtract": True,
                "min-x": -100,
                "max-x": 100,
                "min-z": -200,
                "max-z": 200,
            },
        ]
        render.marker_sets = (
            "{\n"
            "  spawn: {\n"
            '    label: "Spawn"\n'
            "    markers: {}\n"
            "  }\n"
            "}"
        )
        render.save()
        profile = BlueMapProfile.objects.create(name="Default", slug="default")
        render_config = BlueMapRenderConfig.objects.create(render=render, profile=profile)

        content = render_config.generate_content()

        self.assertIn('world="/srv/minecraft/world"', content.replace(": ", "="))
        self.assertIn('storage: "file"', content)
        self.assertIn('sky-color: "#112233"', content)
        self.assertIn('void-color: "#445566"', content)
        self.assertIn("sky-light: 0.75", content)
        self.assertIn("ambient-light: 0.25", content)
        self.assertIn("remove-caves-below-y: 42", content)
        self.assertIn("cave-detection-ocean-floor: -3", content)
        self.assertIn("cave-detection-uses-block-light: true", content)
        self.assertIn("min-inhabited-time: 1200", content)
        self.assertIn("start-pos: { x: 10, y: 80, z: -20 }", content)
        self.assertIn("render-mask: [", content)
        self.assertIn("type: box", content)
        self.assertIn("subtract: true", content)
        self.assertIn("min-x: -100", content)
        self.assertIn("max-z: 200", content)
        self.assertIn("render-edges: false", content)
        self.assertIn("edge-light-strength: 12", content)
        self.assertIn("enable-perspective-view: false", content)
        self.assertIn("enable-flat-view: true", content)
        self.assertIn("enable-free-flight-view: false", content)
        self.assertIn("enable-hires: true", content)
        self.assertIn("ignore-missing-light-data: true", content)
        self.assertIn("marker-sets: {", content)
        self.assertIn('label: "Spawn"', content)
        self.assertNotIn("maps:", content)

    def create_render(self):
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
            bluemap_map_id="overworld-hd",
            display_name="HD 4K",
            dimension=Render.Dimension.OVERWORLD,
        )
        return render

# Create your tests here.


class BlueMapProfilePanelTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="superadmin",
            email="superadmin@example.com",
            password="password-123",
        )
        self.staff = User.objects.create_user(
            username="staff",
            password="password-123",
            is_staff=True,
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.superuser)

    def test_superuser_can_open_bluemap_profiles_page(self):
        response = self.client.get(reverse("bluemap_profiles"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BlueMap Profiles")
        self.assertContains(response, "Create Default Profile")

    def test_panel_settings_links_to_bluemap_profiles(self):
        response = self.client.get(reverse("panel_settings"))

        self.assertContains(response, reverse("bluemap_profiles"))
        self.assertContains(response, "Manage BlueMap Profiles")

    def test_staff_cannot_manage_bluemap_profiles(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("bluemap_profiles"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_create_default_profile_action(self):
        response = self.client.post(reverse("create_default_bluemap_profile"))

        self.assertRedirects(response, reverse("bluemap_profiles"))
        profile = BlueMapProfile.objects.get(slug="default")
        self.assertEqual(profile.name, "Default BlueMap CLI")
        self.assertEqual(profile.command_template, DEFAULT_PROFILE_COMMAND_TEMPLATE)
        self.assertTrue(profile.is_active)

    def test_create_and_edit_bluemap_profile(self):
        form_response = self.client.get(reverse("create_bluemap_profile"))

        self.assertContains(form_response, 'rows="28"')
        self.assertContains(form_response, "min-height: 34rem;")

        create_response = self.client.post(
            reverse("create_bluemap_profile"),
            {
                "name": "Custom CLI",
                "slug": "custom-cli",
                "description": "Custom render settings.",
                "command_template": '"{bluemap_cli}" -c "{config_dir}" -r',
                "config_template": 'world: "{world_path}"\nname: "{display_name}"\n',
                "is_active": "on",
            },
        )

        self.assertRedirects(create_response, reverse("bluemap_profiles"))
        profile = BlueMapProfile.objects.get(slug="custom-cli")

        edit_response = self.client.post(
            reverse("edit_bluemap_profile", kwargs={"profile_id": profile.id}),
            {
                "name": "Custom CLI Updated",
                "slug": "custom-cli",
                "description": "Updated.",
                "command_template": '"{bluemap_cli}" -c "{config_dir}" -r',
                "config_template": 'world: "{world_path}"\ndimension: "{dimension}"\n',
                "is_active": "on",
            },
        )

        self.assertRedirects(edit_response, reverse("bluemap_profiles"))
        profile.refresh_from_db()
        self.assertEqual(profile.name, "Custom CLI Updated")
        self.assertIn('dimension: "{dimension}"', profile.config_template)

    def test_toggle_bluemap_profile_active_state(self):
        profile = BlueMapProfile.objects.create(name="Default", slug="default")

        response = self.client.post(reverse("toggle_bluemap_profile", kwargs={"profile_id": profile.id}))

        self.assertRedirects(response, reverse("bluemap_profiles"))
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)

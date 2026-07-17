from decimal import Decimal

from django.test import TestCase

from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from .models import BlueMapProfile, BlueMapRenderConfig


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
        self.assertIn("render-edges: false", content)
        self.assertIn("edge-light-strength: 12", content)
        self.assertIn("enable-perspective-view: false", content)
        self.assertIn("enable-flat-view: true", content)
        self.assertIn("enable-free-flight-view: false", content)
        self.assertIn("enable-hires: true", content)
        self.assertIn("ignore-missing-light-data: true", content)
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

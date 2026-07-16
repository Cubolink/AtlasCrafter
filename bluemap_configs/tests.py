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
        profile = BlueMapProfile.objects.create(name="Default", slug="default")
        render_config = BlueMapRenderConfig.objects.create(render=render, profile=profile)

        content = render_config.generate_content()

        self.assertIn('world="/srv/minecraft/world"', content.replace(": ", "="))
        self.assertIn('storage: "file"', content)
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

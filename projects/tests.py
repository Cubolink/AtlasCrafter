from django.core.exceptions import ValidationError
from django.test import TestCase

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

# Create your tests here.

from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone


class BlueMapProfile(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    config_template = models.TextField(
        default=(
            'world: "{world_path}"\n'
            'dimension: "{dimension}"\n'
            'name: "{display_name}"\n'
            'sorting: {sorting}\n'
            'start-pos: {{ x: 0, z: 0 }}\n'
            'sky-color: "{sky_color}"\n'
            'void-color: "{void_color}"\n'
            'sky-light: {sky_light}\n'
            'ambient-light: {ambient_light}\n'
            'remove-caves-below-y: {remove_caves_below_y}\n'
            'cave-detection-ocean-floor: {cave_detection_ocean_floor}\n'
            'cave-detection-uses-block-light: {cave_detection_uses_block_light}\n'
            'min-inhabited-time: {min_inhabited_time}\n'
            'render-mask: []\n'
            'render-edges: {render_edges}\n'
            'edge-light-strength: {edge_light_strength}\n'
            'enable-perspective-view: {enable_perspective_view}\n'
            'enable-flat-view: {enable_flat_view}\n'
            'enable-free-flight-view: {enable_free_flight_view}\n'
            'enable-hires: {enable_hires}\n'
            'storage: "{storage}"\n'
            'ignore-missing-light-data: {ignore_missing_light_data}\n'
            'marker-sets: {{}}\n'
        )
    )
    command_template = models.CharField(
        max_length=500,
        default='"{bluemap_cli}" -c "{config_dir}" -r',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BlueMapRenderConfig(models.Model):
    render = models.OneToOneField(
        "projects.Render",
        on_delete=models.CASCADE,
        related_name="config",
    )
    profile = models.ForeignKey(
        BlueMapProfile,
        on_delete=models.PROTECT,
        related_name="render_configs",
    )
    advanced_fields = models.JSONField(default=dict, blank=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)
    adopted_manual_file = models.BooleanField(default=False)

    class Meta:
        ordering = ["render__atlas__project__name", "render__display_name"]

    def __str__(self) -> str:
        return f"Config for {self.render}"

    def context(self) -> dict[str, str]:
        render = self.render
        return {
            "project": render.project.name,
            "atlas": render.atlas.display_name,
            "render": render.display_name,
            "map_id": render.bluemap_map_id,
            "world_path": Path(render.world_folder.source_path).as_posix(),
            "dimension": render.effective_dimension,
            "display_name": render.display_name,
            "sorting": str(render.sorting),
            "sky_color": render.sky_color,
            "void_color": render.void_color,
            "sky_light": format_decimal(render.sky_light),
            "ambient_light": format_decimal(render.ambient_light),
            "remove_caves_below_y": str(render.remove_caves_below_y),
            "cave_detection_ocean_floor": str(render.cave_detection_ocean_floor),
            "cave_detection_uses_block_light": hocon_bool(render.cave_detection_uses_block_light),
            "min_inhabited_time": str(render.min_inhabited_time),
            "render_edges": hocon_bool(render.render_edges),
            "edge_light_strength": str(render.edge_light_strength),
            "enable_perspective_view": hocon_bool(render.enable_perspective_view),
            "enable_flat_view": hocon_bool(render.enable_flat_view),
            "enable_free_flight_view": hocon_bool(render.enable_free_flight_view),
            "enable_hires": hocon_bool(render.enable_hires),
            "storage": render.storage_profile or "file",
            "ignore_missing_light_data": hocon_bool(render.ignore_missing_light_data),
            "bluemap_cli": settings.BLUEMAP_CLI_PATH,
            "config_dir": settings.BLUEMAP_CONFIG_DIR.as_posix(),
            "config_file": self.config_path().as_posix(),
            "webroot_dir": settings.BLUEMAP_WEBROOT_DIR.as_posix(),
        }

    def config_path(self) -> Path:
        return settings.BLUEMAP_CONFIG_DIR / "maps" / f"{self.render.bluemap_map_id}.conf"

    def generate_content(self) -> str:
        header = (
            "# Managed by BlueMap Web UI Panel\n"
            f"# Project: {self.render.project.name}\n"
            f"# Atlas: {self.render.atlas.display_name}\n"
            f"# Render: {self.render.display_name}\n"
            f"# Last generated: {timezone.now().isoformat()}\n\n"
        )
        return header + self.profile.config_template.format(**self.context())


class ConfigRevision(models.Model):
    render_config = models.ForeignKey(
        BlueMapRenderConfig,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    old_content = models.TextField(blank=True)
    new_content = models.TextField()
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Revision for {self.render_config} at {self.created_at:%Y-%m-%d %H:%M:%S}"


class GeneratedConfigFile(models.Model):
    render_config = models.OneToOneField(
        BlueMapRenderConfig,
        on_delete=models.CASCADE,
        related_name="generated_file",
    )
    path = models.CharField(max_length=1024)
    content_hash = models.CharField(max_length=128, blank=True)
    last_written_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["path"]

    def __str__(self) -> str:
        return self.path


def hocon_bool(value: bool) -> str:
    return "true" if value else "false"


def format_decimal(value) -> str:
    return f"{value.normalize():f}"

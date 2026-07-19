from django import forms

from .models import BlueMapProfile


DEFAULT_PROFILE_CONFIG_TEMPLATE = (
    'world: "{world_path}"\n'
    'dimension: "{dimension}"\n'
    'name: "{display_name}"\n'
    'sorting: {sorting}\n'
    'start-pos: {start_pos}\n'
    'sky-color: "{sky_color}"\n'
    'void-color: "{void_color}"\n'
    'sky-light: {sky_light}\n'
    'ambient-light: {ambient_light}\n'
    'remove-caves-below-y: {remove_caves_below_y}\n'
    'cave-detection-ocean-floor: {cave_detection_ocean_floor}\n'
    'cave-detection-uses-block-light: {cave_detection_uses_block_light}\n'
    'min-inhabited-time: {min_inhabited_time}\n'
    'render-mask: {render_mask}\n'
    'render-edges: {render_edges}\n'
    'edge-light-strength: {edge_light_strength}\n'
    'enable-perspective-view: {enable_perspective_view}\n'
    'enable-flat-view: {enable_flat_view}\n'
    'enable-free-flight-view: {enable_free_flight_view}\n'
    'enable-hires: {enable_hires}\n'
    'storage: "{storage}"\n'
    'ignore-missing-light-data: {ignore_missing_light_data}\n'
    'marker-sets: {marker_sets}\n'
)

DEFAULT_PROFILE_COMMAND_TEMPLATE = '"{bluemap_cli}" -c "{config_dir}" -r'


class BlueMapProfileForm(forms.ModelForm):
    class Meta:
        model = BlueMapProfile
        fields = [
            "name",
            "slug",
            "description",
            "command_template",
            "config_template",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "command_template": forms.TextInput(),
            "config_template": forms.Textarea(
                attrs={
                    "rows": 28,
                    "class": "font-mono text-sm",
                    "style": "min-height: 34rem;",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
        }
        help_texts = {
            "slug": "Stable identifier used when assigning this profile to Projects.",
            "command_template": (
                "Command used by the render worker. Template variables include "
                "{bluemap_cli}, {config_dir}, {map_id}, and {webroot_dir}."
            ),
            "config_template": (
                "BlueMap map config template. It is rendered with the fields from the Render form."
            ),
            "is_active": "Inactive profiles stay available for existing records but are skipped as defaults.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "is_active":
                continue
            base_class = "textarea textarea-bordered w-full" if isinstance(
                field.widget, forms.Textarea
            ) else "input input-bordered w-full"
            existing_class = field.widget.attrs.get("class")
            field.widget.attrs["class"] = f"{base_class} {existing_class}".strip()


def default_profile_data() -> dict[str, object]:
    return {
        "name": "Default BlueMap CLI",
        "slug": "default",
        "description": (
            "Default standalone BlueMap CLI profile for AtlasCrafter. Uses the configured "
            "BlueMap CLI jar/path and generated config directory."
        ),
        "config_template": DEFAULT_PROFILE_CONFIG_TEMPLATE,
        "command_template": DEFAULT_PROFILE_COMMAND_TEMPLATE,
        "is_active": True,
    }

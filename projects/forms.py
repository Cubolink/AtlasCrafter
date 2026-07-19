from decimal import Decimal
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.models import ProjectMembership
from .models import Atlas, Project, Render, WorldFolder
from .world_discovery import detect_dimensions, world_folder_exists


RENDER_BASIC_FIELDS = [
    "display_name",
    "dimension",
    "custom_dimension",
    "perspective_preset",
    "sorting",
    "is_enabled",
]
RENDER_ADVANCED_FIELDS = [
    "storage_profile",
    "sky_color",
    "void_color",
    "sky_light",
    "ambient_light",
    "remove_caves_below_y",
    "cave_detection_ocean_floor",
    "cave_detection_uses_block_light",
    "min_inhabited_time",
    "render_edges",
    "edge_light_strength",
    "enable_perspective_view",
    "enable_flat_view",
    "enable_free_flight_view",
    "enable_hires",
    "ignore_missing_light_data",
]

RENDER_PRESET_DEFAULTS = {
    Render.PerspectivePreset.DAY: {
        "sky_color": "#7dabff",
        "void_color": "#000000",
        "sky_light": "1.00",
        "ambient_light": "0.00",
        "remove_caves_below_y": 55,
        "cave_detection_ocean_floor": -5,
        "cave_detection_uses_block_light": False,
        "render_edges": True,
        "edge_light_strength": 8,
        "enable_perspective_view": True,
        "enable_flat_view": True,
        "enable_free_flight_view": True,
        "enable_hires": True,
    },
    Render.PerspectivePreset.NIGHT: {
        "sky_color": "#1d2b53",
        "void_color": "#000000",
        "sky_light": "0.25",
        "ambient_light": "0.05",
        "remove_caves_below_y": 55,
        "cave_detection_ocean_floor": -5,
        "cave_detection_uses_block_light": False,
        "render_edges": True,
        "edge_light_strength": 8,
        "enable_perspective_view": True,
        "enable_flat_view": True,
        "enable_free_flight_view": True,
        "enable_hires": True,
    },
    Render.PerspectivePreset.CAVE: {
        "sky_color": "#0f172a",
        "void_color": "#000000",
        "sky_light": "0.00",
        "ambient_light": "0.50",
        "remove_caves_below_y": -10000,
        "cave_detection_ocean_floor": 10000,
        "cave_detection_uses_block_light": True,
        "render_edges": True,
        "edge_light_strength": 4,
        "enable_perspective_view": True,
        "enable_flat_view": False,
        "enable_free_flight_view": True,
        "enable_hires": True,
    },
    Render.PerspectivePreset.FLAT: {
        "sky_color": "#7dabff",
        "void_color": "#000000",
        "sky_light": "1.00",
        "ambient_light": "0.00",
        "remove_caves_below_y": 55,
        "cave_detection_ocean_floor": -5,
        "cave_detection_uses_block_light": False,
        "render_edges": True,
        "edge_light_strength": 8,
        "enable_perspective_view": False,
        "enable_flat_view": True,
        "enable_free_flight_view": False,
        "enable_hires": True,
    },
}

RENDER_PRESET_SUMMARIES = {
    Render.PerspectivePreset.DAY: "Balanced daylight defaults with all viewer modes enabled.",
    Render.PerspectivePreset.NIGHT: "Darker sky and low ambient light for night-style maps.",
    Render.PerspectivePreset.CAVE: "Brighter cave interiors and cave-focused view defaults.",
    Render.PerspectivePreset.FLAT: "Top-down map defaults with perspective and free-flight disabled.",
    Render.PerspectivePreset.CUSTOM: "Leaves the advanced fields exactly as you set them.",
}

RENDER_PRESET_DECIMAL_FIELDS = {"sky_light", "ambient_light"}


def apply_render_preset_defaults(render: Render) -> None:
    defaults = RENDER_PRESET_DEFAULTS.get(render.perspective_preset, {})
    for field_name, value in defaults.items():
        if field_name in RENDER_PRESET_DECIMAL_FIELDS:
            value = Decimal(value)
        setattr(render, field_name, value)


class AtlasCreateForm(forms.ModelForm):
    class Meta:
        model = Atlas
        fields = ["world_folder", "display_name", "notes"]

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["world_folder"].queryset = project.visible_worlds.filter(is_active=True)
        self.fields["world_folder"].empty_label = "Select a visible world folder"

    def save(self, commit=True):
        atlas = super().save(commit=False)
        atlas.project = self.project
        if commit:
            atlas.save()
        return atlas


class ProjectManageForm(forms.ModelForm):
    visible_worlds = forms.ModelMultipleChoiceField(
        queryset=WorldFolder.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Project
        fields = [
            "name",
            "description",
            "owner_team",
            "is_active",
            "default_bluemap_profile",
            "visible_worlds",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].label = "Active (not archived)"
        if self.instance.pk:
            self.fields["visible_worlds"].queryset = WorldFolder.objects.filter(
                Q(is_active=True) | Q(visible_in_projects=self.instance),
            ).distinct().order_by("display_name")
            self.fields["visible_worlds"].initial = self.instance.visible_worlds.all()
        else:
            self.fields["visible_worlds"].queryset = WorldFolder.objects.filter(
                is_active=True,
            ).order_by("display_name")

    def save(self, commit=True):
        if commit:
            project = super().save(commit=True)
            project.visible_worlds.set(self.cleaned_data["visible_worlds"])
            return project
        return super().save(commit=False)


class WorldFolderForm(forms.ModelForm):
    class Meta:
        model = WorldFolder
        fields = ["display_name", "source_path", "is_active", "notes"]

    def clean_source_path(self):
        source_path = Path(self.cleaned_data["source_path"]).expanduser().resolve()
        if self.cleaned_data.get("is_active", True) and not (source_path / "level.dat").is_file():
            raise forms.ValidationError("This folder does not contain level.dat.")
        return str(source_path)

    def save(self, commit=True):
        world = super().save(commit=False)
        if world_folder_exists(world):
            world.detected_dimensions = detect_dimensions(Path(world.source_path))
        if commit:
            world.save()
        return world


class AtlasEditForm(forms.ModelForm):
    class Meta:
        model = Atlas
        fields = ["display_name", "notes", "is_active"]


class RenderCreateForm(forms.ModelForm):
    class Meta:
        model = Render
        fields = [
            "display_name",
            "dimension",
            "custom_dimension",
            "perspective_preset",
            "sorting",
        ]

    def __init__(self, *args, atlas: Atlas, **kwargs):
        super().__init__(*args, **kwargs)
        self.atlas = atlas
        self.fields["dimension"].initial = Render.Dimension.OVERWORLD
        self.fields["perspective_preset"].initial = Render.PerspectivePreset.DAY
        apply_render_form_attrs(self.fields)

    def save(self, commit=True):
        render = super().save(commit=False)
        render.atlas = self.atlas
        apply_render_preset_defaults(render)
        if commit:
            render.save()
        return render


class RenderEditForm(forms.ModelForm):
    class Meta:
        model = Render
        fields = RENDER_BASIC_FIELDS + RENDER_ADVANCED_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_render_form_attrs(self.fields)
        for field_name in ["sky_color", "void_color"]:
            self.fields[field_name].widget.attrs.update(
                {
                    "pattern": r"^#[0-9a-fA-F]{6}$",
                    "placeholder": "#7dabff",
                    "data-color-value": "",
                }
            )
        for field_name in [
            "is_enabled",
            "cave_detection_uses_block_light",
            "render_edges",
            "enable_perspective_view",
            "enable_flat_view",
            "enable_free_flight_view",
            "enable_hires",
            "ignore_missing_light_data",
        ]:
            self.fields[field_name].widget.attrs["class"] = "toggle toggle-primary"
        self.fields["sky_light"].widget.attrs.update(
            {"min": "0", "max": "1", "step": "0.05", "data-range-value": ""}
        )
        self.fields["ambient_light"].widget.attrs.update(
            {"min": "0", "max": "1", "step": "0.05", "data-range-value": ""}
        )
        self.fields["edge_light_strength"].widget.attrs.update(
            {"min": "0", "max": "15", "step": "1", "data-range-value": ""}
        )


def apply_render_form_attrs(fields):
    help_texts = {
        "display_name": "Name shown for this map in the BlueMap web viewer.",
        "dimension": "Choose a vanilla dimension, or Custom for a mod/datapack dimension key.",
        "custom_dimension": "Only used when Dimension is Custom. Example: minecraft:overworld or a mod/datapack key.",
        "perspective_preset": "Preset defaults for the advanced render fields. Custom keeps your manual values.",
        "sorting": "Lower numbers appear earlier in BlueMap map lists.",
        "is_enabled": "Disabled renders are hidden from normal project views and cannot be opened.",
        "storage_profile": "BlueMap storage config id. Leave blank to use the default file storage.",
        "sky_color": "Sky color used by the map, as a hex color.",
        "void_color": "Void/background color used by the map, as a hex color.",
        "sky_light": "Initial sky light strength in the viewer. 0 is dark, 1 is fully lit.",
        "ambient_light": "Base light applied everywhere. 0 is none, 1 is fully lit.",
        "remove_caves_below_y": "Below this Y level, BlueMap may remove cave faces that are not visible from above.",
        "cave_detection_ocean_floor": "Ocean-floor-relative Y offset where cave detection starts.",
        "cave_detection_uses_block_light": "Also use block light when deciding whether an area is a cave.",
        "min_inhabited_time": "Only render chunks players have spent at least this many ticks near.",
        "render_edges": "Render solid-looking edges where a render mask cuts the world.",
        "edge_light_strength": "Light level applied to rendered map edges. BlueMap expects 0 to 15.",
        "enable_perspective_view": "Enable BlueMap's 3D perspective view for this render.",
        "enable_flat_view": "Enable BlueMap's flat/top-down view for this render.",
        "enable_free_flight_view": "Enable free-flight camera mode for this render.",
        "enable_hires": "Enable high-resolution tiles. Disabling can reduce render time and storage size.",
        "ignore_missing_light_data": "Render chunks even when Minecraft light data is missing.",
    }
    for field_name, help_text in help_texts.items():
        if field_name in fields:
            fields[field_name].help_text = help_text

    fields["dimension"].widget.attrs["data-dimension-select"] = ""
    fields["perspective_preset"].widget.attrs["data-perspective-preset"] = ""
    fields["custom_dimension"].label = "Custom dimension key"
    fields["custom_dimension"].widget.attrs.update(
        {
            "placeholder": "modid:dimension_name",
            "data-custom-dimension": "",
        }
    )
    if "storage_profile" in fields:
        fields["storage_profile"].label = "Storage config id"
        fields["storage_profile"].widget.attrs["placeholder"] = "file"


class ProjectUserAddForm(forms.Form):
    user_lookup = forms.CharField(
        label="Username or email",
        max_length=254,
        help_text="Enter an exact username or email for an existing user.",
    )

    def __init__(self, *args, project: Project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.user = None

    def clean_user_lookup(self):
        lookup = self.cleaned_data["user_lookup"].strip()
        User = get_user_model()

        username_matches = list(User.objects.filter(username=lookup))
        if username_matches:
            user = username_matches[0]
        else:
            email_matches = list(User.objects.filter(email__iexact=lookup))
            if not email_matches:
                raise forms.ValidationError("No user exists with that username or email.")
            if len(email_matches) > 1:
                raise forms.ValidationError(
                    "Multiple users have that email. Use the exact username instead."
                )
            user = email_matches[0]

        if ProjectMembership.objects.filter(project=self.project, user=user).exists():
            raise forms.ValidationError("That user already has access to this Project.")

        self.user = user
        return lookup

    def save(self):
        return ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.PROJECT_USER,
        )

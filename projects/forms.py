import re
from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.models import ProjectMembership
from .models import Atlas, MinecraftResourceSource, Project, Render, WorldFolder
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
    "start_x",
    "start_y",
    "start_z",
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
    "render_mask_type",
    "render_mask_subtract",
    "render_mask_min_x",
    "render_mask_max_x",
    "render_mask_min_y",
    "render_mask_max_y",
    "render_mask_min_z",
    "render_mask_max_z",
    "render_mask_center_x",
    "render_mask_center_z",
    "render_mask_radius",
    "marker_sets",
]
RENDER_RESOURCE_FIELDS = [
    "resource_mode",
    "resource_source",
    "custom_mods_path",
    "minecraft_version_override",
]

RENDER_MASK_TYPES = [
    ("none", "No mask"),
    ("box", "Box"),
    ("circle", "Circle"),
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
        fields = [
            "display_name",
            "source_path",
            "default_resource_source",
            "is_active",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_resource_source"].queryset = MinecraftResourceSource.objects.filter(
            is_active=True
        )
        self.fields["default_resource_source"].required = False
        self.fields["default_resource_source"].help_text = (
            "Optional mod resources used by default for Renders of this world."
        )

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


class MinecraftResourceSourceForm(forms.ModelForm):
    class Meta:
        model = MinecraftResourceSource
        fields = [
            "display_name",
            "root_path",
            "mods_path",
            "minecraft_version",
            "mod_loader",
            "load_mod_resources_by_default",
            "auto_detect",
            "is_active",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["root_path"].help_text = (
            "Folder containing this server, modpack, or Minecraft instance."
        )
        self.fields["mods_path"].help_text = "Folder containing the mod JAR files."
        self.fields["minecraft_version"].help_text = "Version passed to BlueMap, such as 1.20.1."
        self.fields["auto_detect"].help_text = (
            "Refresh detected paths, version, and loader during source scans."
        )
        for field_name in ["load_mod_resources_by_default", "auto_detect", "is_active"]:
            self.fields[field_name].widget.attrs["class"] = "toggle toggle-primary"

    def clean_root_path(self):
        return validate_resource_path(self.cleaned_data["root_path"], "Resource root")

    def clean_mods_path(self):
        value = self.cleaned_data.get("mods_path", "").strip()
        if not value:
            return ""
        path = validate_resource_path(value, "Mods folder")
        if not any(Path(path).glob("*.jar")):
            raise forms.ValidationError("This folder does not contain any mod JAR files.")
        return path

    def clean_minecraft_version(self):
        version = self.cleaned_data.get("minecraft_version", "").strip()
        if version and not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            raise forms.ValidationError("Enter a Minecraft version such as 1.20.1.")
        return version

    def save(self, commit=True):
        source = super().save(commit=False)
        if not source.pk:
            source.source_type = MinecraftResourceSource.SourceType.CUSTOM
            source.is_detected = False
            source.auto_detect = False
        if commit:
            source.save()
        return source


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
    start_x = forms.IntegerField(required=False, label="Start X")
    start_y = forms.IntegerField(required=False, label="Start Y")
    start_z = forms.IntegerField(required=False, label="Start Z")
    render_mask_type = forms.ChoiceField(
        choices=RENDER_MASK_TYPES,
        required=False,
        label="Render mask type",
    )
    render_mask_subtract = forms.BooleanField(
        required=False,
        label="Subtract mask",
    )
    render_mask_min_x = forms.IntegerField(required=False, label="Min X")
    render_mask_max_x = forms.IntegerField(required=False, label="Max X")
    render_mask_min_y = forms.IntegerField(required=False, label="Min Y")
    render_mask_max_y = forms.IntegerField(required=False, label="Max Y")
    render_mask_min_z = forms.IntegerField(required=False, label="Min Z")
    render_mask_max_z = forms.IntegerField(required=False, label="Max Z")
    render_mask_center_x = forms.IntegerField(required=False, label="Center X")
    render_mask_center_z = forms.IntegerField(required=False, label="Center Z")
    render_mask_radius = forms.IntegerField(required=False, min_value=1, label="Radius")

    class Meta:
        model = Render
        fields = [
            *RENDER_BASIC_FIELDS,
            *RENDER_RESOURCE_FIELDS,
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
            "marker_sets",
        ]
        widgets = {
            "marker_sets": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, allow_custom_paths=False, **kwargs):
        self.allow_custom_paths = allow_custom_paths
        super().__init__(*args, **kwargs)
        apply_render_form_attrs(self.fields)
        self.fields["resource_source"].queryset = MinecraftResourceSource.objects.filter(
            is_active=True
        )
        self.fields["resource_mode"].required = False
        self.fields["resource_source"].required = False
        self.fields["resource_mode"].widget.attrs["data-resource-mode"] = ""
        self.fields["resource_source"].widget.attrs["data-resource-source"] = ""
        self.fields["custom_mods_path"].widget.attrs["data-custom-mods-path"] = ""
        self.fields["minecraft_version_override"].widget.attrs.update(
            {"placeholder": "For example, 1.20.1"}
        )
        self.fields["resource_mode"].help_text = (
            "Inherit the world default, disable mods, or choose another registered source."
        )
        self.fields["minecraft_version_override"].help_text = (
            "Leave blank to use the selected or inherited source version."
        )
        if not allow_custom_paths and self.instance.resource_mode == Render.ResourceMode.CUSTOM:
            self.fields["resource_mode"].disabled = True
            self.fields["custom_mods_path"].disabled = True
        elif not allow_custom_paths:
            self.fields["resource_mode"].choices = [
                choice
                for choice in self.fields["resource_mode"].choices
                if choice[0] != Render.ResourceMode.CUSTOM
            ]
        self.set_config_initials()
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
            "render_mask_subtract",
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
        self.fields["render_mask_type"].widget.attrs["data-render-mask-type"] = ""
        self.fields["marker_sets"].widget.attrs.update(
            {
                "class": "textarea textarea-bordered min-h-48 w-full font-mono text-sm",
                "placeholder": "{}",
            }
        )

    def set_config_initials(self):
        start_position = self.instance.start_position or {}
        self.fields["start_x"].initial = start_position.get("x")
        self.fields["start_y"].initial = start_position.get("y")
        self.fields["start_z"].initial = start_position.get("z")

        render_mask = self.instance.render_mask or []
        mask = render_mask[0] if render_mask else {}
        mask_type = mask.get("type", "box") if mask else "none"
        if mask_type not in {"box", "circle"}:
            mask_type = "none"
        self.fields["render_mask_type"].initial = mask_type
        self.fields["render_mask_subtract"].initial = mask.get("subtract", False)
        for field_name, mask_key in [
            ("render_mask_min_x", "min-x"),
            ("render_mask_max_x", "max-x"),
            ("render_mask_min_y", "min-y"),
            ("render_mask_max_y", "max-y"),
            ("render_mask_min_z", "min-z"),
            ("render_mask_max_z", "max-z"),
            ("render_mask_center_x", "center-x"),
            ("render_mask_center_z", "center-z"),
            ("render_mask_radius", "radius"),
        ]:
            self.fields[field_name].initial = mask.get(mask_key)

    def clean(self):
        cleaned_data = super().clean()
        resource_mode = cleaned_data.get("resource_mode") or Render.ResourceMode.INHERIT
        cleaned_data["resource_mode"] = resource_mode
        if resource_mode == Render.ResourceMode.SOURCE and not cleaned_data.get("resource_source"):
            self.add_error("resource_source", "Choose a registered resource source.")
        if resource_mode == Render.ResourceMode.CUSTOM:
            if not self.allow_custom_paths:
                self.add_error("resource_mode", "Only superadministrators can use custom paths.")
            custom_path = cleaned_data.get("custom_mods_path", "").strip()
            if not custom_path:
                self.add_error("custom_mods_path", "Enter the folder containing the mod JAR files.")
            else:
                try:
                    cleaned_data["custom_mods_path"] = validate_resource_path(
                        custom_path,
                        "Custom mods folder",
                    )
                except forms.ValidationError as exc:
                    self.add_error("custom_mods_path", exc)
                else:
                    if not any(Path(cleaned_data["custom_mods_path"]).glob("*.jar")):
                        self.add_error(
                            "custom_mods_path",
                            "This folder does not contain any mod JAR files.",
                        )
        version = cleaned_data.get("minecraft_version_override", "").strip()
        if version and not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            self.add_error(
                "minecraft_version_override",
                "Enter a Minecraft version such as 1.20.1.",
            )
        mask_type = cleaned_data.get("render_mask_type")
        if mask_type not in {"box", "circle"}:
            cleaned_data["render_mask_type"] = "none"
            return cleaned_data
        if mask_type == "circle":
            for field_name in ["render_mask_center_x", "render_mask_center_z", "render_mask_radius"]:
                if cleaned_data.get(field_name) is None:
                    self.add_error(field_name, "Circle masks require center X, center Z, and radius.")
        return cleaned_data

    def save(self, commit=True):
        render = super().save(commit=False)
        if render.resource_mode != Render.ResourceMode.SOURCE:
            render.resource_source = None
        if render.resource_mode != Render.ResourceMode.CUSTOM:
            render.custom_mods_path = ""
        render.start_position = self.build_start_position()
        render.render_mask = self.build_render_mask()
        if commit:
            render.save()
        return render

    def build_start_position(self):
        start_position = {}
        for field_name, key in [("start_x", "x"), ("start_y", "y"), ("start_z", "z")]:
            value = self.cleaned_data.get(field_name)
            if value is not None:
                start_position[key] = value
        return start_position

    def build_render_mask(self):
        mask_type = self.cleaned_data.get("render_mask_type")
        if mask_type not in {"box", "circle"}:
            return []

        mask = {"type": mask_type}
        if self.cleaned_data.get("render_mask_subtract"):
            mask["subtract"] = True

        if mask_type == "box":
            for field_name, key in [
                ("render_mask_min_x", "min-x"),
                ("render_mask_max_x", "max-x"),
                ("render_mask_min_y", "min-y"),
                ("render_mask_max_y", "max-y"),
                ("render_mask_min_z", "min-z"),
                ("render_mask_max_z", "max-z"),
            ]:
                value = self.cleaned_data.get(field_name)
                if value is not None:
                    mask[key] = value
        elif mask_type == "circle":
            for field_name, key in [
                ("render_mask_center_x", "center-x"),
                ("render_mask_center_z", "center-z"),
                ("render_mask_radius", "radius"),
                ("render_mask_min_y", "min-y"),
                ("render_mask_max_y", "max-y"),
            ]:
                value = self.cleaned_data.get(field_name)
                if value is not None:
                    mask[key] = value

        return [mask]


def validate_resource_path(value: str, label: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise forms.ValidationError(f"{label} does not exist or is not a folder.")

    allowed_roots = [
        Path(settings.SOURCE_WORLDS_DIR).resolve(),
        Path(settings.BLUEMAP_RESOURCE_SOURCES_DIR).resolve(),
    ]
    if not any(path == root or path.is_relative_to(root) for root in allowed_roots):
        raise forms.ValidationError(
            f"{label} must be inside SOURCE_WORLDS_DIR or BLUEMAP_RESOURCE_SOURCES_DIR."
        )
    return str(path)


def apply_render_form_attrs(fields):
    help_texts = {
        "display_name": "Name shown for this map in the BlueMap web viewer.",
        "dimension": "Choose a vanilla dimension, or Custom for a mod/datapack dimension key.",
        "custom_dimension": "Only used when Dimension is Custom. Example: minecraft:overworld or a mod/datapack key.",
        "perspective_preset": "Preset defaults for the advanced render fields. Custom keeps your manual values.",
        "sorting": "Lower numbers appear earlier in BlueMap map lists.",
        "is_enabled": "Disabled renders are hidden from normal project views and cannot be opened.",
        "storage_profile": "BlueMap storage config id. Leave blank to use the default file storage.",
        "start_x": "Optional map center X coordinate when the render is opened.",
        "start_y": "Optional map center Y coordinate when the render is opened.",
        "start_z": "Optional map center Z coordinate when the render is opened.",
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
        "render_mask_type": "Limit or subtract a coordinate area from this render.",
        "render_mask_subtract": "When enabled, BlueMap excludes the mask area instead of rendering only that area.",
        "render_mask_min_x": "Optional box minimum X coordinate.",
        "render_mask_max_x": "Optional box maximum X coordinate.",
        "render_mask_min_y": "Optional minimum Y coordinate.",
        "render_mask_max_y": "Optional maximum Y coordinate.",
        "render_mask_min_z": "Optional box minimum Z coordinate.",
        "render_mask_max_z": "Optional box maximum Z coordinate.",
        "render_mask_center_x": "Circle mask center X coordinate.",
        "render_mask_center_z": "Circle mask center Z coordinate.",
        "render_mask_radius": "Circle mask radius in blocks.",
        "marker_sets": "Raw BlueMap marker-sets HOCON. Use {} when this render has no static markers.",
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

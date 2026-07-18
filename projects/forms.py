from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from pathlib import Path

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

    def save(self, commit=True):
        render = super().save(commit=False)
        render.atlas = self.atlas
        if commit:
            render.save()
        return render


class RenderEditForm(forms.ModelForm):
    class Meta:
        model = Render
        fields = RENDER_BASIC_FIELDS + RENDER_ADVANCED_FIELDS


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

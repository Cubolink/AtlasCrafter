from django import forms
from django.contrib.auth import get_user_model

from accounts.models import ProjectMembership
from .models import Atlas, Project, Render


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
        fields = [
            "display_name",
            "dimension",
            "custom_dimension",
            "perspective_preset",
            "sorting",
            "is_enabled",
        ]


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

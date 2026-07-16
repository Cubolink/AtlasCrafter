from django import forms

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

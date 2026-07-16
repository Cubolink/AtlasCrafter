from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from projects.models import Project
from .models import ProjectMembership


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["username", "email"]


class PanelUserCreateForm(forms.ModelForm):
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput,
        help_text="The user should change this after signing in.",
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "password"]

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class PanelUserEditForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].disabled = True


class ProjectAccessForm(forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["project", "role"]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        assigned_project_ids = ProjectMembership.objects.filter(user=user).values_list(
            "project_id",
            flat=True,
        )
        self.fields["project"].queryset = Project.objects.exclude(
            id__in=assigned_project_ids,
        ).order_by("name")

    def save(self, commit=True):
        membership = super().save(commit=False)
        membership.user = self.user
        if commit:
            membership.save()
        return membership

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password


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

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BlueMapProfileForm, default_profile_data
from .models import BlueMapProfile


def superuser_required(user):
    return user.is_authenticated and user.is_superuser


@login_required
@user_passes_test(superuser_required)
def bluemap_profiles(request):
    profiles = BlueMapProfile.objects.all()
    has_default_profile = BlueMapProfile.objects.filter(slug="default").exists()
    return render(
        request,
        "bluemap_configs/profiles.html",
        {
            "profiles": profiles,
            "has_default_profile": has_default_profile,
        },
    )


@login_required
@user_passes_test(superuser_required)
def create_bluemap_profile(request):
    form = BlueMapProfileForm()
    if request.method == "POST":
        form = BlueMapProfileForm(request.POST)
        if form.is_valid():
            profile = form.save()
            messages.success(request, f"BlueMap profile '{profile.name}' created.")
            return redirect("bluemap_profiles")

    return render_profile_form(request, form, "Create BlueMap Profile", "Create Profile")


@login_required
@user_passes_test(superuser_required)
def edit_bluemap_profile(request, profile_id: int):
    profile = get_object_or_404(BlueMapProfile, id=profile_id)
    form = BlueMapProfileForm(instance=profile)
    if request.method == "POST":
        form = BlueMapProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            messages.success(request, f"BlueMap profile '{profile.name}' updated.")
            return redirect("bluemap_profiles")

    return render_profile_form(request, form, "Edit BlueMap Profile", "Save Profile")


@login_required
@user_passes_test(superuser_required)
@require_POST
def create_default_bluemap_profile(request):
    profile, created = BlueMapProfile.objects.get_or_create(
        slug="default",
        defaults=default_profile_data(),
    )
    if created:
        messages.success(request, "Default BlueMap CLI profile created.")
    else:
        messages.info(request, f"Default profile already exists as '{profile.name}'.")
    return redirect("bluemap_profiles")


@login_required
@user_passes_test(superuser_required)
@require_POST
def toggle_bluemap_profile(request, profile_id: int):
    profile = get_object_or_404(BlueMapProfile, id=profile_id)
    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active", "updated_at"])
    state = "activated" if profile.is_active else "deactivated"
    messages.success(request, f"BlueMap profile '{profile.name}' {state}.")
    return redirect("bluemap_profiles")


def render_profile_form(request, form, title, submit_label):
    return render(
        request,
        "bluemap_configs/profile_form.html",
        {
            "form": form,
            "title": title,
            "submit_label": submit_label,
        },
    )

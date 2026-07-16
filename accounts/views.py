from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AccountProfileForm, PanelUserCreateForm, PanelUserEditForm


def can_access_panel_settings(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def profile_settings(request):
    profile_form = AccountProfileForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == "POST":
        form_name = request.POST.get("form")
        if form_name == "profile":
            profile_form = AccountProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile settings updated.")
                return redirect("profile_settings")
        elif form_name == "password":
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed.")
                return redirect("profile_settings")
        else:
            messages.error(request, "Unknown settings form.")

    return render(
        request,
        "accounts/profile_settings.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


@login_required
@user_passes_test(can_access_panel_settings)
def panel_settings(request):
    query = request.GET.get("q", "").strip()
    users = get_user_model().objects.order_by("username")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
        )

    return render(
        request,
        "accounts/panel_settings.html",
        {
            "query": query,
            "users": users,
        },
    )


@login_required
@user_passes_test(can_access_panel_settings)
def panel_user_create(request):
    form = PanelUserCreateForm()
    if request.method == "POST":
        form = PanelUserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User '{user.username}' created.")
            return redirect("panel_settings")

    return render(
        request,
        "accounts/panel_user_form.html",
        {
            "form": form,
            "title": "Add New User",
            "submit_label": "Create User",
        },
    )


@login_required
@user_passes_test(can_access_panel_settings)
def panel_user_edit(request, user_id: int):
    user = get_object_or_404(get_user_model(), id=user_id)
    form = PanelUserEditForm(instance=user)
    if request.method == "POST":
        form = PanelUserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User '{user.username}' updated.")
            return redirect("panel_settings")

    return render(
        request,
        "accounts/panel_user_form.html",
        {
            "form": form,
            "title": "Edit User",
            "submit_label": "Save User",
        },
    )

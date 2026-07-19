from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from renders.models import RenderJob
from .forms import AccountProfileForm, PanelUserCreateForm, PanelUserEditForm, ProjectAccessForm
from .models import ProjectMembership


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
    return render(request, "accounts/panel_settings.html")


@login_required
@user_passes_test(can_access_panel_settings)
def panel_jobs(request):
    jobs = RenderJob.objects.select_related(
        "render__atlas__project",
        "requested_by",
    )
    active_jobs = jobs.filter(
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).order_by("created_at")
    finished_jobs = jobs.exclude(
        status__in=[RenderJob.Status.QUEUED, RenderJob.Status.RUNNING],
    ).order_by("-finished_at", "-updated_at")[:25]

    return render(
        request,
        "accounts/panel_jobs.html",
        {
            "active_jobs": active_jobs,
            "finished_jobs": finished_jobs,
        },
    )


@login_required
@user_passes_test(can_access_panel_settings)
def panel_users(request):
    query = request.GET.get("q", "").strip()
    users = get_user_model().objects.order_by("username")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
        )

    return render(
        request,
        "accounts/panel_users.html",
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
            return redirect("panel_users")

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
            return redirect("panel_users")

    return render(
        request,
        "accounts/panel_user_form.html",
        {
            "form": form,
            "project_access_form": ProjectAccessForm(user=user) if request.user.is_superuser else None,
            "memberships": user.project_memberships.select_related("project").all(),
            "edited_user": user,
            "title": "Edit User",
            "submit_label": "Save User",
        },
    )


@login_required
@user_passes_test(lambda user: user.is_superuser)
@require_POST
def panel_user_project_access_add(request, user_id: int):
    user = get_object_or_404(get_user_model(), id=user_id)
    form = ProjectAccessForm(request.POST, user=user)
    if form.is_valid():
        membership = form.save()
        messages.success(
            request,
            f"Added {user.username} to {membership.project.name} as {membership.get_role_display()}.",
        )
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect("panel_user_edit", user_id=user.id)


@login_required
@user_passes_test(lambda user: user.is_superuser)
@require_POST
def panel_user_project_access_remove(request, user_id: int, membership_id: int):
    user = get_object_or_404(get_user_model(), id=user_id)
    membership = get_object_or_404(ProjectMembership, id=membership_id, user=user)
    project_name = membership.project.name
    membership.delete()
    messages.success(request, f"Removed {user.username} from {project_name}.")
    return redirect("panel_user_edit", user_id=user.id)

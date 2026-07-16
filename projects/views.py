from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from accounts.models import ProjectMembership
from .models import Project


@login_required
def dashboard(request):
    if request.user.is_superuser:
        projects = Project.objects.prefetch_related("atlases__renders").all()
    else:
        project_ids = ProjectMembership.objects.filter(user=request.user).values_list(
            "project_id",
            flat=True,
        )
        projects = Project.objects.filter(id__in=project_ids).prefetch_related("atlases__renders")

    return render(request, "projects/dashboard.html", {"projects": projects})


@login_required
def project_detail(request, slug: str):
    project = get_object_or_404(
        Project.objects.prefetch_related("atlases__renders", "visible_worlds"),
        slug=slug,
    )
    if not request.user.is_superuser:
        get_object_or_404(ProjectMembership, user=request.user, project=project)

    return render(request, "projects/project_detail.html", {"project": project})

# Create your views here.

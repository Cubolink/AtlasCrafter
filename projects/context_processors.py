from accounts.models import ProjectMembership
from projects.models import Project


def sidebar_projects(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"sidebar_projects": []}

    projects = Project.objects.filter(is_active=True).order_by("name")
    if not user.is_superuser:
        project_ids = ProjectMembership.objects.filter(user=user).values_list(
            "project_id",
            flat=True,
        )
        projects = projects.filter(id__in=project_ids)

    return {"sidebar_projects": projects}

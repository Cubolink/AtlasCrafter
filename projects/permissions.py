from accounts.models import ProjectMembership
from .models import Project


def can_manage_project(user, project: Project) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return ProjectMembership.objects.filter(
        user=user,
        project=project,
        role=ProjectMembership.Role.PROJECT_ADMINISTRATOR,
    ).exists()

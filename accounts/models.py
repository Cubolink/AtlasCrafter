from django.conf import settings
from django.db import models


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        PROJECT_ADMINISTRATOR = "project_administrator", "Project Administrator"
        PROJECT_USER = "project_user", "Project User"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "project")]
        ordering = ["project__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} as {self.get_role_display()} in {self.project}"

# Create your models here.

from django.db import models


class RenderSchedule(models.Model):
    render = models.ForeignKey(
        "projects.Render",
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    name = models.CharField(max_length=160)
    cron_expression = models.CharField(max_length=120, blank=True)
    interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    retry_failures = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["render__atlas__project__name", "name"]

    def __str__(self) -> str:
        return f"{self.name} for {self.render}"

# Create your models here.

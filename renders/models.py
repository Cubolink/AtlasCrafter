from django.db import models


class RenderJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    render = models.ForeignKey(
        "projects.Render",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    command = models.JSONField(default=list, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    progress = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    requested_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_render_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.render} ({self.get_status_display()})"


class RenderLogChunk(models.Model):
    job = models.ForeignKey(RenderJob, on_delete=models.CASCADE, related_name="log_chunks")
    stream = models.CharField(max_length=10, choices=[("stdout", "stdout"), ("stderr", "stderr")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.stream} chunk for job {self.job_id}"


class RenderArtifact(models.Model):
    job = models.ForeignKey(RenderJob, on_delete=models.CASCADE, related_name="artifacts")
    path = models.CharField(max_length=1024)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["path"]

    def __str__(self) -> str:
        return self.path

# Create your models here.

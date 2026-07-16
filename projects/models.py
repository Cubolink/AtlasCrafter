import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


def generate_bluemap_map_id() -> str:
    return f"render-{uuid.uuid4()}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class WorldFolder(TimeStampedModel):
    display_name = models.CharField(max_length=160)
    source_path = models.CharField(max_length=1024, unique=True)
    detected_dimensions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class Project(TimeStampedModel):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    owner_team = models.CharField(max_length=160, blank=True)
    default_bluemap_profile = models.ForeignKey(
        "bluemap_configs.BlueMapProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_projects",
    )
    output_path = models.CharField(max_length=1024, blank=True)
    visible_worlds = models.ManyToManyField(
        WorldFolder,
        through="ProjectVisibleWorld",
        related_name="visible_in_projects",
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        permissions = [
            ("assign_project_users", "Can assign users to project roles"),
            ("manage_project_visible_worlds", "Can manage visible world folders"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"slug": self.slug})


class ProjectVisibleWorld(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    world_folder = models.ForeignKey(WorldFolder, on_delete=models.CASCADE)
    made_visible_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visible_world_assignments",
    )

    class Meta:
        unique_together = [("project", "world_folder")]
        ordering = ["project__name", "world_folder__display_name"]

    def __str__(self) -> str:
        return f"{self.world_folder} visible in {self.project}"


class Atlas(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="atlases")
    world_folder = models.ForeignKey(WorldFolder, on_delete=models.PROTECT, related_name="atlases")
    display_name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("project", "slug")]
        ordering = ["project__name", "display_name"]
        permissions = [
            ("manage_atlas", "Can manage atlas"),
        ]

    def clean(self):
        if self.project_id and self.world_folder_id:
            is_visible = ProjectVisibleWorld.objects.filter(
                project=self.project,
                world_folder=self.world_folder,
            ).exists()
            if not is_visible:
                raise ValidationError(
                    "This world folder is not visible to the selected project."
                )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.display_name)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.project} / {self.display_name}"


class Region(TimeStampedModel):
    name = models.CharField(max_length=160)
    min_x = models.IntegerField()
    min_z = models.IntegerField()
    max_x = models.IntegerField()
    max_z = models.IntegerField()
    min_y = models.IntegerField(null=True, blank=True)
    max_y = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Render(TimeStampedModel):
    class Dimension(models.TextChoices):
        OVERWORLD = "minecraft:overworld", "Overworld"
        NETHER = "minecraft:the_nether", "The Nether"
        END = "minecraft:the_end", "The End"
        CUSTOM = "custom", "Custom"

    class PerspectivePreset(models.TextChoices):
        DAY = "day", "Day"
        NIGHT = "night", "Night"
        CAVE = "cave", "Cave"
        FLAT = "flat", "Flat"
        CUSTOM = "custom", "Custom"

    atlas = models.ForeignKey(Atlas, on_delete=models.CASCADE, related_name="renders")
    bluemap_map_id = models.SlugField(
        max_length=180,
        unique=True,
        editable=False,
        default=generate_bluemap_map_id,
    )
    display_name = models.CharField(max_length=160)
    dimension = models.CharField(max_length=80, choices=Dimension.choices)
    custom_dimension = models.CharField(max_length=160, blank=True)
    sorting = models.IntegerField(default=0)
    perspective_preset = models.CharField(
        max_length=20,
        choices=PerspectivePreset.choices,
        default=PerspectivePreset.DAY,
    )
    start_position = models.JSONField(default=dict, blank=True)
    lighting_options = models.JSONField(default=dict, blank=True)
    cave_options = models.JSONField(default=dict, blank=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True)
    storage_profile = models.CharField(max_length=160, blank=True)
    output_path = models.CharField(max_length=1024, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["atlas__project__name", "atlas__display_name", "sorting", "display_name"]
        permissions = [
            ("manage_render", "Can manage render"),
            ("trigger_render", "Can trigger render"),
        ]

    def clean(self):
        if self.dimension != self.Dimension.CUSTOM and self.custom_dimension:
            raise ValidationError("Custom dimension should only be set for custom renders.")
        if self.dimension == self.Dimension.CUSTOM and not self.custom_dimension:
            raise ValidationError("Custom renders require a custom dimension key.")

    def save(self, *args, **kwargs):
        if not self.bluemap_map_id:
            self.bluemap_map_id = generate_bluemap_map_id()
        super().save(*args, **kwargs)

    @property
    def project(self):
        return self.atlas.project

    @property
    def world_folder(self):
        return self.atlas.world_folder

    @property
    def effective_dimension(self) -> str:
        if self.dimension == self.Dimension.CUSTOM:
            return self.custom_dimension
        return self.dimension

    def __str__(self) -> str:
        return f"{self.atlas} / {self.display_name}"

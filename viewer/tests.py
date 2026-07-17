from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ProjectMembership
from bluemap_configs.models import BlueMapProfile, BlueMapRenderConfig, ConfigRevision, GeneratedConfigFile
from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from renders.models import RenderJob, RenderLogChunk


class RenderViewerStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        self.project = Project.objects.create(name="Survival Server")
        self.world = WorldFolder.objects.create(
            display_name="Overworld",
            source_path="/srv/minecraft/world",
        )
        ProjectVisibleWorld.objects.create(project=self.project, world_folder=self.world)
        self.atlas = Atlas.objects.create(
            project=self.project,
            world_folder=self.world,
            display_name="Overworld",
        )
        self.render = Render.objects.create(
            atlas=self.atlas,
            bluemap_map_id="overworld",
            display_name="Overworld",
            dimension=Render.Dimension.OVERWORLD,
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)

    def test_render_page_disables_trigger_button_for_active_job(self):
        RenderJob.objects.create(render=self.render, status=RenderJob.Status.RUNNING)

        response = self.client.get(reverse("render_viewer", kwargs={"render_id": self.render.id}))

        self.assertContains(response, "Render in progress")
        self.assertContains(response, "disabled")

    def test_trigger_redirects_without_duplicate_when_active_job_exists(self):
        RenderJob.objects.create(render=self.render, status=RenderJob.Status.QUEUED)

        response = self.client.post(reverse("trigger_render", kwargs={"render_id": self.render.id}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.render.jobs.count(), 1)

    def test_render_status_reports_active_job(self):
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.RUNNING)

        response = self.client.get(reverse("render_status", kwargs={"render_id": self.render.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["has_active_job"], True)
        self.assertEqual(response.json()["job"]["id"], job.id)
        self.assertEqual(response.json()["job"]["status"], RenderJob.Status.RUNNING)

    def test_render_status_reports_latest_finished_job_without_active_job(self):
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.SUCCEEDED)

        response = self.client.get(reverse("render_status", kwargs={"render_id": self.render.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["has_active_job"], False)
        self.assertEqual(response.json()["job"]["id"], job.id)
        self.assertEqual(response.json()["job"]["status"], RenderJob.Status.SUCCEEDED)

    def test_render_page_links_to_job_detail(self):
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.SUCCEEDED)

        response = self.client.get(reverse("render_viewer", kwargs={"render_id": self.render.id}))

        self.assertContains(response, reverse("render_job_detail", kwargs={"job_id": job.id}))
        self.assertContains(response, "View details and logs")

    def test_job_detail_shows_logs_and_cancel_for_queued_job(self):
        job = RenderJob.objects.create(
            render=self.render,
            status=RenderJob.Status.QUEUED,
            requested_by=self.user,
        )
        RenderLogChunk.objects.create(job=job, stream="stderr", content="Something happened")

        response = self.client.get(reverse("render_job_detail", kwargs={"job_id": job.id}))

        self.assertContains(response, "Render Job")
        self.assertContains(response, "Something happened")
        self.assertContains(response, reverse("cancel_render_job", kwargs={"job_id": job.id}))

    def test_superuser_can_cancel_queued_job(self):
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.QUEUED)

        response = self.client.post(reverse("cancel_render_job", kwargs={"job_id": job.id}))

        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, RenderJob.Status.CANCELED)
        self.assertIsNotNone(job.finished_at)

    def test_running_job_cannot_be_canceled(self):
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.RUNNING)

        response = self.client.post(reverse("cancel_render_job", kwargs={"job_id": job.id}))

        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, RenderJob.Status.RUNNING)
        self.assertIsNone(job.finished_at)

    def test_project_user_can_view_but_not_cancel_job(self):
        project_user = User.objects.create_user(username="viewer", password="password")

        ProjectMembership.objects.create(
            user=project_user,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_USER,
        )
        job = RenderJob.objects.create(render=self.render, status=RenderJob.Status.QUEUED)
        self.client.force_login(project_user)

        detail_response = self.client.get(reverse("render_job_detail", kwargs={"job_id": job.id}))
        cancel_response = self.client.post(reverse("cancel_render_job", kwargs={"job_id": job.id}))

        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(detail_response, "Cancel queued job")
        self.assertEqual(cancel_response.status_code, 403)
        job.refresh_from_db()
        self.assertEqual(job.status, RenderJob.Status.QUEUED)

    def test_render_page_links_to_config_preview_for_admin(self):
        BlueMapProfile.objects.create(name="Default", slug="default")

        response = self.client.get(reverse("render_viewer", kwargs={"render_id": self.render.id}))

        self.assertContains(
            response,
            reverse("render_config_preview", kwargs={"render_id": self.render.id}),
        )

    def test_admin_can_preview_generated_render_config(self):
        BlueMapProfile.objects.create(name="Default", slug="default")
        self.render.sky_color = "#112233"
        self.render.save()

        response = self.client.get(
            reverse("render_config_preview", kwargs={"render_id": self.render.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('sky-color: "#112233"', response.context["config_content"])
        self.assertIn('world: "/srv/minecraft/world"', response.context["config_content"])

    def test_config_preview_does_not_write_generated_file_or_revision(self):
        BlueMapProfile.objects.create(name="Default", slug="default")

        response = self.client.get(
            reverse("render_config_preview", kwargs={"render_id": self.render.id})
        )

        self.assertEqual(response.status_code, 200)
        render_config = BlueMapRenderConfig.objects.get(render=self.render)
        self.assertFalse(ConfigRevision.objects.filter(render_config=render_config).exists())
        self.assertFalse(GeneratedConfigFile.objects.filter(render_config=render_config).exists())

    def test_project_user_cannot_preview_render_config(self):
        project_user = User.objects.create_user(username="viewer2", password="password")
        ProjectMembership.objects.create(
            user=project_user,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_USER,
        )
        self.client.force_login(project_user)

        response = self.client.get(
            reverse("render_config_preview", kwargs={"render_id": self.render.id})
        )

        self.assertEqual(response.status_code, 403)

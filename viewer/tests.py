from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from renders.models import RenderJob


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

# Create your tests here.

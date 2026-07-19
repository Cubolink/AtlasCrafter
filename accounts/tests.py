from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from projects.models import Atlas, Project, ProjectVisibleWorld, Render, WorldFolder
from renders.models import RenderJob
from .models import ProjectMembership


class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="old-password-123",
            email="old@example.com",
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.user)

    def test_username_links_to_profile_settings(self):
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, reverse("profile_settings"))
        self.assertContains(response, self.user.username)

    def test_profile_settings_requires_login(self):
        anonymous = Client(HTTP_HOST="localhost")

        response = anonymous.get(reverse("profile_settings"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_user_can_update_profile_settings(self):
        response = self.client.post(
            reverse("profile_settings"),
            {
                "form": "profile",
                "username": "new-admin",
                "email": "new@example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "new-admin")
        self.assertEqual(self.user.email, "new@example.com")

    def test_user_can_clear_optional_email(self):
        response = self.client.post(
            reverse("profile_settings"),
            {
                "form": "profile",
                "username": "admin",
                "email": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "")

    def test_user_can_change_password_and_stay_logged_in(self):
        response = self.client.post(
            reverse("profile_settings"),
            {
                "form": "password",
                "old_password": "old-password-123",
                "new_password1": "new-password-456",
                "new_password2": "new-password-456",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password-456"))

        response = self.client.get(reverse("profile_settings"))
        self.assertEqual(response.status_code, 200)


class PanelSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="staff-admin",
            password="password-123",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username="project-user",
            password="password-123",
            email="user@example.com",
        )
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.admin)

    def test_staff_user_sees_panel_settings_link(self):
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, reverse("panel_settings"))
        self.assertContains(response, "Panel Settings")

    def test_non_staff_user_cannot_access_panel_settings(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("panel_settings"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_panel_users_lists_and_searches_users(self):
        response = self.client.get(reverse("panel_users"), {"q": "project"})

        self.assertContains(response, "project-user")
        self.assertContains(response, "user@example.com")
        self.assertNotContains(response, "<td>staff-admin</td>", html=True)

    def test_panel_settings_links_to_users_page(self):
        response = self.client.get(reverse("panel_settings"))

        self.assertContains(response, reverse("panel_users"))
        self.assertContains(response, "Manage Users")

    def test_panel_settings_links_to_render_jobs_page(self):
        response = self.client.get(reverse("panel_settings"))

        self.assertContains(response, reverse("panel_jobs"))
        self.assertContains(response, "View Render Jobs")

    def test_panel_jobs_lists_active_and_finished_jobs(self):
        render = self.create_render()
        queued_job = RenderJob.objects.create(
            render=render,
            requested_by=self.admin,
            status=RenderJob.Status.QUEUED,
        )
        finished_job = RenderJob.objects.create(
            render=render,
            requested_by=self.user,
            status=RenderJob.Status.SUCCEEDED,
        )

        response = self.client.get(reverse("panel_jobs"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{queued_job.id}")
        self.assertContains(response, f"#{finished_job.id}")
        self.assertContains(response, "Queued")
        self.assertContains(response, "Succeeded")
        self.assertContains(response, render.display_name)

    def test_staff_user_can_open_panel_job_detail(self):
        render = self.create_render()
        job = RenderJob.objects.create(render=render, status=RenderJob.Status.RUNNING)

        response = self.client.get(reverse("render_job_detail", kwargs={"job_id": job.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Render Job #{job.id}")

    def test_non_staff_user_cannot_access_panel_jobs(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("panel_jobs"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_staff_user_can_create_user(self):
        response = self.client.post(
            reverse("panel_user_create"),
            {
                "username": "new-user",
                "password": "created-password-123",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("created-password-123"))

    def test_staff_user_can_update_user_email_but_not_username(self):
        response = self.client.post(
            reverse("panel_user_edit", kwargs={"user_id": self.user.id}),
            {
                "username": "renamed-user",
                "email": "updated@example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "project-user")
        self.assertEqual(self.user.email, "updated@example.com")

    def test_superuser_can_assign_project_access_to_user(self):
        superuser = User.objects.create_superuser(
            username="superadmin",
            password="password-123",
        )
        project = Project.objects.create(name="Survival")
        self.client.force_login(superuser)

        response = self.client.post(
            reverse("panel_user_project_access_add", kwargs={"user_id": self.user.id}),
            {
                "project": project.id,
                "role": ProjectMembership.Role.PROJECT_ADMINISTRATOR,
            },
        )

        self.assertEqual(response.status_code, 302)
        membership = ProjectMembership.objects.get(user=self.user, project=project)
        self.assertEqual(membership.role, ProjectMembership.Role.PROJECT_ADMINISTRATOR)

    def test_superuser_can_remove_project_access_from_user(self):
        superuser = User.objects.create_superuser(
            username="superadmin",
            password="password-123",
        )
        project = Project.objects.create(name="Survival")
        membership = ProjectMembership.objects.create(
            user=self.user,
            project=project,
            role=ProjectMembership.Role.PROJECT_USER,
        )
        self.client.force_login(superuser)

        response = self.client.post(
            reverse(
                "panel_user_project_access_remove",
                kwargs={"user_id": self.user.id, "membership_id": membership.id},
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectMembership.objects.filter(id=membership.id).exists())

    def test_staff_user_cannot_assign_project_administrator_access(self):
        project = Project.objects.create(name="Survival")

        response = self.client.post(
            reverse("panel_user_project_access_add", kwargs={"user_id": self.user.id}),
            {
                "project": project.id,
                "role": ProjectMembership.Role.PROJECT_ADMINISTRATOR,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectMembership.objects.filter(user=self.user, project=project).exists())

    def create_render(self):
        project = Project.objects.create(name="Survival")
        world = WorldFolder.objects.create(
            display_name="Overworld",
            source_path="/srv/minecraft/world",
        )
        ProjectVisibleWorld.objects.create(project=project, world_folder=world)
        atlas = Atlas.objects.create(
            project=project,
            world_folder=world,
            display_name="Overworld",
        )
        return Render.objects.create(
            atlas=atlas,
            display_name="Spawn Render",
            bluemap_map_id="spawn_render",
        )

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


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

    def test_panel_settings_lists_and_searches_users(self):
        response = self.client.get(reverse("panel_settings"), {"q": "project"})

        self.assertContains(response, "project-user")
        self.assertContains(response, "user@example.com")
        self.assertNotContains(response, "<td>staff-admin</td>", html=True)

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

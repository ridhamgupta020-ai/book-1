from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch
from .firebase_auth import InvalidFirebaseToken
from .models import UserProfile


class UserAuthTestCase(TestCase):
    def test_registration_and_login_flow(self):
        response = self.client.post(
            reverse("users:register"),
            {
                "username": "rohan_k",
                "email": "rohan@example.com",
                "first_name": "Rohan",
                "last_name": "Kapoor",
                "password1": "CinemaPass2026!",
                "password2": "CinemaPass2026!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="rohan_k").exists())

    def test_booking_history_requires_authentication(self):
        response = self.client.get(reverse("bookings:my_bookings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_login_page_renders_firebase_google_sign_in(self):
        response = self.client.get(reverse("users:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "firebase-web-config")
        self.assertContains(response, "name=\"csrfmiddlewaretoken\"")

    @patch("users.views.verify_firebase_id_token")
    def test_google_sign_in_links_existing_verified_email(self, verify_token):
        user = User.objects.create_user(
            username="legacy-user",
            email="google@example.com",
            password="ExistingPass2026!",
        )
        verify_token.return_value = {
            "uid": "firebase-user-1",
            "email": "google@example.com",
            "email_verified": True,
            "name": "Google User",
            "firebase": {"sign_in_provider": "google.com"},
        }

        response = self.client.post(
            reverse("users:google_session"),
            {"id_token": "verified-test-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("movies:home"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(
            UserProfile.objects.get(user=user).firebase_uid, "firebase-user-1"
        )
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), user.pk
        )

    @patch("users.views.verify_firebase_id_token")
    def test_google_sign_in_reuses_firebase_identity(self, verify_token):
        verify_token.return_value = {
            "uid": "firebase-user-2",
            "email": "new-google@example.com",
            "email_verified": True,
            "name": "New Google User",
            "firebase": {"sign_in_provider": "google.com"},
        }
        url = reverse("users:google_session")

        first_response = self.client.post(
            url, {"id_token": "verified-test-token"}
        )
        second_response = self.client.post(
            url, {"id_token": "verified-test-token"}
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(User.objects.filter(email="new-google@example.com").count(), 1)
        self.assertEqual(
            UserProfile.objects.filter(firebase_uid="firebase-user-2").count(), 1
        )

    @patch("users.views.verify_firebase_id_token", side_effect=InvalidFirebaseToken)
    def test_google_sign_in_rejects_invalid_token(self, verify_token):
        response = self.client.post(
            reverse("users:google_session"),
            {"id_token": "invalid-test-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False)
    def test_google_session_requires_csrf(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("users:google_session"),
            {"id_token": "verified-test-token"},
        )

        self.assertEqual(response.status_code, 403)

    @patch("users.views.verify_firebase_id_token")
    def test_google_sign_in_rejects_non_google_provider(self, verify_token):
        verify_token.return_value = {
            "uid": "firebase-user-3",
            "email": "password-user@example.com",
            "email_verified": True,
            "firebase": {"sign_in_provider": "password"},
        }

        response = self.client.post(
            reverse("users:google_session"),
            {"id_token": "verified-test-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.exists())

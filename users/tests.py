import re
from urllib.parse import urlsplit

from django.core import mail
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
        user = User.objects.get(username="rohan_k")
        self.assertTrue(user.check_password("CinemaPass2026!"))
        self.client.post(reverse("users:logout"))
        response = self.client.post(
            reverse("users:login"),
            {"username": "rohan_k", "password": "CinemaPass2026!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            user.pk,
        )
        self.assertEqual(
            self.client.get(reverse("bookings:my_bookings")).status_code, 200
        )

    def test_login_rejects_invalid_password_without_case_folding(self):
        User.objects.create_user(
            username="case-sensitive-user",
            password="CinemaPass2026!",
        )

        valid_response = self.client.post(
            reverse("users:login"),
            {"username": "case-sensitive-user", "password": "CinemaPass2026!"},
        )
        self.assertEqual(valid_response.status_code, 302)

        self.client.post(reverse("users:logout"))
        invalid_response = self.client.post(
            reverse("users:login"),
            {"username": "case-sensitive-user", "password": "cinemapass2026!"},
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(
            invalid_response,
            "Please enter a correct username and password",
        )

    def test_registration_rejects_duplicate_username_and_case_insensitive_email(self):
        User.objects.create_user(
            username="existing-user",
            email="existing@example.com",
            password="CinemaPass2026!",
        )
        register_url = reverse("users:register")
        duplicate_username = self.client.post(
            register_url,
            {
                "username": "existing-user",
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "User",
                "password1": "AnotherPass2026!",
                "password2": "AnotherPass2026!",
            },
        )
        duplicate_email = self.client.post(
            register_url,
            {
                "username": "another-user",
                "email": "EXISTING@example.com",
                "first_name": "Another",
                "last_name": "User",
                "password1": "AnotherPass2026!",
                "password2": "AnotherPass2026!",
            },
        )

        self.assertEqual(duplicate_username.status_code, 200)
        self.assertEqual(duplicate_email.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_applies_password_validation(self):
        response = self.client.post(
            reverse("users:register"),
            {
                "username": "short-password-user",
                "email": "short@example.com",
                "first_name": "Short",
                "last_name": "Password",
                "password1": "123",
                "password2": "123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="short-password-user").exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_is_generic_and_uses_a_working_timed_token(self):
        user = User.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="OriginalPass2026!",
        )
        reset_url = reverse("users:password_reset")

        unknown_response = self.client.post(
            reset_url, {"email": "nobody@example.com"}
        )
        self.assertEqual(unknown_response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(
            self.client.get(reverse("users:password_reset_done")),
            "If an account exists",
        )

        response = self.client.post(reset_url, {"email": user.email})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(response.url, unknown_response.url)
        self.assertIn("password-reset/confirm/", mail.outbox[0].body)

        confirm_link = next(
            line
            for line in mail.outbox[0].body.splitlines()
            if "password-reset/confirm/" in line
        )
        confirm_url = urlsplit(confirm_link).path
        confirm_response = self.client.get(confirm_url)
        self.assertEqual(confirm_response.status_code, 302)
        confirm_response = self.client.get(confirm_response.url)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "Choose a New Password")

        response = self.client.post(
            confirm_response.request["PATH_INFO"],
            {
                "new_password1": "UpdatedPassword2026!",
                "new_password2": "UpdatedPassword2026!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("UpdatedPassword2026!"))
        self.assertFalse(user.check_password("OriginalPass2026!"))
        response = self.client.post(
            reverse("users:login"),
            {"username": user.username, "password": "UpdatedPassword2026!"},
        )
        self.assertEqual(response.status_code, 302)

    def test_booking_history_requires_authentication(self):
        response = self.client.get(reverse("bookings:my_bookings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_login_page_renders_firebase_google_sign_in(self):
        response = self.client.get(reverse("users:login"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Cross-Origin-Opener-Policy"],
            "same-origin-allow-popups",
        )
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "firebase-web-config")
        self.assertContains(response, "name=\"csrfmiddlewaretoken\"")

    @override_settings(
        FIREBASE_WEB_CONFIG={
            "apiKey": "",
            "authDomain": "",
            "projectId": "",
            "storageBucket": "",
            "messagingSenderId": "",
            "appId": "",
        }
    )
    def test_google_sign_in_is_disabled_when_web_config_is_missing(self):
        response = self.client.get(reverse("users:login"))

        self.assertContains(response, "Google sign-in is not configured")
        self.assertRegex(
            response.content.decode(),
            re.compile(r'<button\s+id="google-sign-in".*?disabled', re.DOTALL),
        )

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

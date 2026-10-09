from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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

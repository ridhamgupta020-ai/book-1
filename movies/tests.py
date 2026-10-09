from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Movie, Screen, Seat, Show, Theatre


class MovieAndShowTestCase(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            title="Chronos Horizon",
            description="Deep space time-dilation expedition thriller.",
            genre="Sci-Fi",
            language="English",
            duration_minutes=148,
            release_date=date.today(),
            certificate=Movie.Certificate.UA,
            cast="Aarav Mehta, Elena Vance",
            director="Vikramaditya Sen",
            status=Movie.Status.NOW_SHOWING,
            is_featured=True,
        )
        self.theatre = Theatre.objects.create(
            name="MyBookShow Grand IMAX",
            city="Mumbai",
            address="Lower Parel, Mumbai",
        )
        self.screen = Screen.objects.create(
            theatre=self.theatre,
            name="Audi 1 IMAX Laser",
            total_rows=2,
            seats_per_row=4,
        )
        for row in ["A", "B"]:
            for num in range(1, 5):
                Seat.objects.create(
                    screen=self.screen,
                    row_label=row,
                    seat_number=num,
                    seat_type=Seat.SeatCategory.STANDARD,
                )

    def test_movie_listing_and_search_filter(self):
        response = self.client.get(reverse("movies:movie_list"), {"q": "Chronos", "genre": "Sci-Fi"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chronos Horizon")

    def test_prevent_overlapping_shows_on_same_screen(self):
        start = timezone.now() + timedelta(hours=3)
        end = start + timedelta(hours=2, minutes=30)
        Show.objects.create(
            movie=self.movie,
            screen=self.screen,
            start_time=start,
            end_time=end,
            ticket_price=Decimal("320.00"),
        )
        overlapping_show = Show(
            movie=self.movie,
            screen=self.screen,
            start_time=start + timedelta(minutes=30),
            end_time=end + timedelta(minutes=30),
            ticket_price=Decimal("320.00"),
        )
        with self.assertRaises(ValidationError):
            overlapping_show.clean()

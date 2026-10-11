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
        self.assertContains(response, "movie-poster")
        self.assertContains(response, 'loading="lazy"')

    def test_movie_search_is_title_only_and_returns_live_count(self):
        self.movie.cast = "Chronos"
        self.movie.save(update_fields=["cast"])

        count_response = self.client.get(
            reverse("movies:movie_list"),
            {"q": "Chronos", "count_only": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(count_response.status_code, 200)
        self.assertEqual(count_response.json(), {"count": 0})

    def test_movie_filters_by_release_rating_theatre_and_showtime(self):
        self.movie.rating = Decimal("8.5")
        self.movie.save(update_fields=["rating"])
        show_start = timezone.localtime(timezone.now()).replace(
            hour=19, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        Show.objects.create(
            movie=self.movie,
            screen=self.screen,
            start_time=show_start,
            end_time=show_start + timedelta(hours=2),
            ticket_price=Decimal("320.00"),
        )

        response = self.client.get(
            reverse("movies:movie_list"),
            {
                "city": self.theatre.city,
                "theatre": self.theatre.id,
                "min_rating": "8.0",
                "showtime": "evening",
                "release_from": date.today().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">1</span> matching movies")

        no_match = self.client.get(
            reverse("movies:movie_list"),
            {
                "city": self.theatre.city,
                "theatre": self.theatre.id,
                "showtime": "morning",
            },
        )
        self.assertContains(no_match, ">0</span> matching movies")

    def test_recently_viewed_movie_drives_recommendations(self):
        related_movie = Movie.objects.create(
            title="Chronos Returns",
            description="A time-bending sequel.",
            genre=self.movie.genre,
            language=self.movie.language,
            duration_minutes=110,
            release_date=date.today(),
            cast="New Cast",
            director="New Director",
        )
        self.client.get(reverse("movies:movie_detail", kwargs={"slug": self.movie.slug}))

        response = self.client.get(reverse("movies:movie_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recommended for You")
        self.assertContains(response, related_movie.title)

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

import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.conf import settings
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from bookings.models import Booking, BookingSeat, PaymentAttempt
from movies.models import Movie, Screen, Seat, Show, ShowSeat, Theatre


urlpatterns = [
    path("analytics/", include(("analytics.urls", "analytics"), namespace="analytics")),
]

TEST_TEMPLATES = [
    {
        **settings.TEMPLATES[0],
        "DIRS": [
            Path(__file__).resolve().parent / "templates",
            *settings.TEMPLATES[0]["DIRS"],
        ],
    }
]


@override_settings(
    ROOT_URLCONF="analytics.tests",
    LOGIN_URL="/login/",
    TEMPLATES=TEST_TEMPLATES,
)
class AnalyticsViewsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._context_copy_patch = patch(
            "django.test.client.copy", side_effect=lambda context: context
        )
        cls._context_copy_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls._context_copy_patch.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="analytics-staff", password="test-password", is_staff=True
        )
        cls.customer = User.objects.create_user(
            username="analytics-customer", password="test-password"
        )
        movie_columns = (
            "title",
            "slug",
            "description",
            "poster",
            "poster_url",
            "genre",
            "language",
            "duration_minutes",
            "release_date",
            "rating",
            "certificate",
            "cast",
            "director",
            "status",
            "is_featured",
            "trailer_url",
            "created_at",
        )
        quoted_movie_columns = ", ".join(
            connection.ops.quote_name(column) for column in movie_columns
        )
        movie_values = [
            "Analytics Feature",
            "analytics-feature",
            "A test feature.",
            "",
            "",
            "Drama",
            "English",
            100,
            date(2025, 1, 1),
            Decimal("0.0"),
            "UA",
            "Cast",
            "Director",
            Movie.Status.NOW_SHOWING,
            False,
            "",
            timezone.now(),
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {connection.ops.quote_name('movies_movie')} "
                f"({quoted_movie_columns}) VALUES "
                f"({', '.join(['%s'] * len(movie_columns))})",
                movie_values,
            )
        movie_id = Movie.objects.filter(slug="analytics-feature").values_list(
            "pk", flat=True
        ).get()
        cls.movie = Movie(pk=movie_id, title="Analytics Feature")
        cls.theatre = Theatre.objects.create(
            name="Central Cinema", city="Delhi", address="Main Road"
        )
        cls.screen = Screen.objects.create(
            theatre=cls.theatre, name="Screen 1", total_rows=1, seats_per_row=3
        )
        cls.seats = [
            Seat.objects.create(
                screen=cls.screen, row_label="A", seat_number=number
            )
            for number in range(1, 4)
        ]

    def setUp(self):
        self.client.force_login(self.staff)
        self.report_day = timezone.localdate()
        show_start = timezone.make_aware(
            datetime.combine(self.report_day, time(20, 0))
        )
        self.show = Show.objects.create(
            movie=self.movie,
            screen=self.screen,
            start_time=show_start,
            end_time=show_start + timedelta(hours=2),
            ticket_price=Decimal("100.00"),
        )
        self.show_seats = [
            ShowSeat.objects.create(show=self.show, seat=seat)
            for seat in self.seats
        ]
        self.show_seats[0].status = ShowSeat.Status.BOOKED
        self.show_seats[0].save(update_fields=["status"])
        self.show_seats[1].status = ShowSeat.Status.HELD
        self.show_seats[1].save(update_fields=["status"])

        now = timezone.now()
        booking_columns = (
            "booking_reference",
            "user_id",
            "show_id",
            "subtotal_amount",
            "convenience_fee",
            "total_amount",
            "status",
            "payment_status",
            "payment_Order_id",
            "payment_transaction_id",
            "expires_at",
            "created_at",
            "updated_at",
        )
        quoted_columns = ", ".join(
            connection.ops.quote_name(column) for column in booking_columns
        )
        placeholders = ", ".join(["%s"] * len(booking_columns))
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {connection.ops.quote_name('bookings_booking')} "
                f"({quoted_columns}) VALUES ({placeholders})",
                [
                    "MBS-ANALYTICS",
                    self.customer.pk,
                    self.show.pk,
                    Decimal("100.00"),
                    Decimal("8.00"),
                    Decimal("108.00"),
                    Booking.Status.CONFIRMED,
                    Booking.PaymentStatus.PAID,
                    "",
                    "",
                    None,
                    now,
                    now,
                ],
            )
        self.booking_id = Booking.objects.filter(
            booking_reference="MBS-ANALYTICS"
        ).values_list("pk", flat=True).get()
        BookingSeat.objects.create(
            booking_id=self.booking_id,
            show_seat=self.show_seats[0],
            price=Decimal("100.00"),
        )

    def _dates(self):
        return {"start_date": self.report_day.isoformat(), "end_date": self.report_day.isoformat()}

    def test_dashboard_aggregates_paid_revenue_booking_state_rankings_and_occupancy(self):
        response = self.client.get(reverse("analytics:dashboard"), self._dates())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gross captured")
        self.assertContains(response, "108.00")
        self.assertContains(response, "Paid, confirmed bookings")
        self.assertContains(response, "Booked / sellable seats")
        self.assertContains(response, "1 / 3")

    def test_dashboard_reports_net_revenue_after_refunds_and_operational_metrics(self):
        booking = Booking.objects.get(pk=self.booking_id)
        booking.payment_status = Booking.PaymentStatus.PARTIALLY_REFUNDED
        booking.save(update_fields=["payment_status"])
        PaymentAttempt.objects.create(
            booking=booking,
            gateway_order_id="order-analytics-refund",
            gateway_payment_id="payment-analytics-refund",
            amount=Decimal("108.00"),
            status=PaymentAttempt.Status.PARTIALLY_REFUNDED,
            refunded_amount=Decimal("20.00"),
            refunded_at=timezone.now(),
        )
        response = self.client.get(reverse("analytics:dashboard"), self._dates())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹108.00")
        self.assertContains(response, "₹20.00")
        self.assertContains(response, "₹88.00")
        self.assertContains(response, "Daily net revenue")
        self.assertContains(response, "Peak booking hours")
        self.assertContains(response, "Registered users")

    def test_non_staff_users_cannot_access_dashboard_or_csv(self):
        self.client.force_login(self.customer)
        self.assertEqual(
            self.client.get(reverse("analytics:dashboard")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("analytics:export_bookings_csv")).status_code, 403
        )

    def test_anonymous_users_are_redirected_for_both_endpoints(self):
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("analytics:dashboard")).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("analytics:export_bookings_csv")).status_code, 302
        )

    def test_invalid_dates_and_oversized_ranges_are_rejected(self):
        bad_date = {"start_date": "2026-02-30", "end_date": "2026-03-01"}
        self.assertEqual(
            self.client.get(reverse("analytics:dashboard"), bad_date).status_code, 400
        )
        self.assertEqual(
            self.client.get(reverse("analytics:export_bookings_csv"), bad_date).status_code,
            400,
        )
        oversized = {"start_date": "2025-01-01", "end_date": "2026-01-02"}
        self.assertEqual(
            self.client.get(reverse("analytics:dashboard"), oversized).status_code, 400
        )
        reversed_dates = {"start_date": "2026-03-02", "end_date": "2026-03-01"}
        self.assertEqual(
            self.client.get(reverse("analytics:export_bookings_csv"), reversed_dates).status_code,
            400,
        )

    def test_csv_streams_booking_rows_and_escapes_formula_leading_text(self):
        self.movie.title = "=2+2"
        self.movie.save(update_fields=["title"])
        response = self.client.get(
            reverse("analytics:export_bookings_csv"), self._dates()
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertIn("text/csv", response["Content-Type"])
        csv_text = b"".join(response.streaming_content).decode("utf-8")
        parsed = list(csv.reader(StringIO(csv_text)))
        self.assertEqual(parsed[0][0], "created_at")
        self.assertEqual(parsed[1][2], "'=2+2")
        self.assertEqual(parsed[1][8], "1")

    def test_default_range_is_valid_and_renders(self):
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'value="{(self.report_day - timedelta(days=29)).isoformat()}"'
        )
        self.assertContains(response, f'value="{self.report_day.isoformat()}"')

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from movies.models import Movie, Screen, Seat, Show, ShowSeat, Theatre
from .models import Booking
from .payments import PaymentGatewayService


class BookingConcurrencyAndPaymentTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="arjun", password="StrongPassword123!")
        self.user2 = User.objects.create_user(username="meera", password="StrongPassword123!")
        self.movie = Movie.objects.create(
            title="Velvet Nocturne",
            description="Neo-noir mystery.",
            genre="Crime",
            language="Hindi",
            duration_minutes=132,
            release_date=date.today(),
            cast="Kabir Bedi, Tara Sharma",
            director="Anurag Kashyap",
        )
        self.theatre = Theatre.objects.create(
            name="Regal Plaza Cinema", city="Delhi", address="Connaught Place"
        )
        self.screen = Screen.objects.create(
            theatre=self.theatre, name="Screen 1", total_rows=1, seats_per_row=2
        )
        self.seat_a1 = Seat.objects.create(
            screen=self.screen, row_label="A", seat_number=1
        )
        self.seat_a2 = Seat.objects.create(
            screen=self.screen, row_label="A", seat_number=2
        )
        start = timezone.now() + timedelta(hours=6)
        self.show = Show.objects.create(
            movie=self.movie,
            screen=self.screen,
            start_time=start,
            end_time=start + timedelta(hours=2, minutes=15),
            ticket_price=Decimal("250.00"),
        )
        self.show.initialize_show_seats()
        self.show_seat_a1 = ShowSeat.objects.get(show=self.show, seat=self.seat_a1)

    def test_double_booking_prevention_and_idempotent_payment(self):
        booking1 = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        # Second user attempting to reserve the same held seat must fail
        with self.assertRaises(ValidationError):
            Booking.create_pending_booking(
                user=self.user2,
                show=self.show,
                show_seat_ids=[self.show_seat_a1.id],
            )

        # Verify payment callback with valid HMAC signature
        order = PaymentGatewayService.create_payment_order(booking1)
        sig = PaymentGatewayService.generate_gateway_signature(
            order_id=order["order_id"],
            transaction_id="TXN-999",
            amount=order["amount"],
        )
        confirmed = PaymentGatewayService.verify_and_confirm_payment(
            booking=booking1,
            order_id=order["order_id"],
            transaction_id="TXN-999",
            signature=sig,
        )
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)

        # Idempotent second callback must succeed without error
        confirmed_again = PaymentGatewayService.verify_and_confirm_payment(
            booking=booking1,
            order_id=order["order_id"],
            transaction_id="TXN-999",
            signature=sig,
        )
        self.assertEqual(confirmed_again.status, Booking.Status.CONFIRMED)

        # Cancellation releases the seat back to AVAILABLE
        cancelled = confirmed.cancel_booking()
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.show_seat_a1.refresh_from_db()
        self.assertEqual(self.show_seat_a1.status, ShowSeat.Status.AVAILABLE)

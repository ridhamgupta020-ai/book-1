from datetime import date, timedelta
from decimal import Decimal
from django.core import mail
from django.core import signing
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
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
        self.user1.email = "arjun@example.com"
        self.user1.save(update_fields=["email"])

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

    def _confirm_booking(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        signature = PaymentGatewayService.generate_gateway_signature(
            order_id=order["order_id"],
            transaction_id="TXN-TICKET-1",
            amount=order["amount"],
        )
        return PaymentGatewayService.verify_and_confirm_payment(
            booking=booking,
            order_id=order["order_id"],
            transaction_id="TXN-TICKET-1",
            signature=signature,
        )

    def test_confirmation_queues_ticket_email_after_commit(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        signature = PaymentGatewayService.generate_gateway_signature(
            order_id=order["order_id"],
            transaction_id="TXN-TICKET-2",
            amount=order["amount"],
        )
        with patch("bookings.tasks.send_booking_ticket_email.delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                PaymentGatewayService.verify_and_confirm_payment(
                    booking=booking,
                    order_id=order["order_id"],
                    transaction_id="TXN-TICKET-2",
                    signature=signature,
                )
        enqueue.assert_called_once_with(booking.pk)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_ticket_email_contains_pdf_attachment(self):
        from .tasks import send_booking_ticket_email

        booking = self._confirm_booking()
        sent = send_booking_ticket_email.run(booking.pk)

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user1.email])
        self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")
        self.assertTrue(mail.outbox[0].attachments[0][1].startswith(b"%PDF-"))

    def test_owner_can_download_pdf_and_qr_verifies_booking(self):
        booking = self._confirm_booking()
        self.client.force_login(self.user1)
        download = self.client.get(
            reverse(
                "bookings:ticket_download",
                kwargs={"booking_reference": booking.booking_reference},
            )
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertTrue(download.content.startswith(b"%PDF-"))

        token = signing.dumps(
            {
                "booking_id": booking.pk,
                "payment_reference": booking.payment_transaction_id,
            },
            salt="bookings.ticket-verification",
        )
        verification = self.client.get(
            reverse("bookings:verify_ticket"), {"token": token}
        )
        self.assertEqual(verification.status_code, 200)
        self.assertContains(verification, "Verified Booking")

        self.client.force_login(self.user2)
        denied = self.client.get(
            reverse(
                "bookings:ticket_download",
                kwargs={"booking_reference": booking.booking_reference},
            )
        )
        self.assertEqual(denied.status_code, 404)

import json
from datetime import date, timedelta
from decimal import Decimal
from django.core import mail
from django.core import signing
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import Mock, patch
from movies.models import Movie, Screen, Seat, Show, ShowSeat, Theatre
from .models import Booking, BookingSeat, PaymentAttempt
from .payments import PaymentGatewayService


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test-secret",
)
class BookingConcurrencyAndPaymentTestCase(TestCase):
    def setUp(self):
        self.gateway_client = Mock()
        self.gateway_client.order.create.side_effect = self._create_gateway_order
        self.gateway_client.payment.refund.return_value = {
            "id": "rfnd_test_1",
            "status": "processed",
            "amount": 27000,
        }
        self.gateway_payments = {}
        self.order_count = 0
        self.gateway_client.payment.fetch.side_effect = (
            lambda payment_id: self.gateway_payments[payment_id]
        )
        client_patcher = patch(
            "bookings.payments.razorpay.Client", return_value=self.gateway_client
        )
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

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
        self.show_seat_a2 = ShowSeat.objects.get(show=self.show, seat=self.seat_a2)
        self.user1.email = "arjun@example.com"
        self.user1.save(update_fields=["email"])

    def _create_gateway_order(self, data):
        self.order_count += 1
        return {
            "id": f"order_{data['receipt']}_{self.order_count}",
            "amount": data["amount"],
            "currency": data["currency"],
        }

    def _verify_payment(self, booking, order, payment_id):
        self.gateway_payments[payment_id] = {
            "id": payment_id,
            "order_id": order["order_id"],
            "status": "captured",
            "currency": order["currency"],
            "amount": order["amount_paise"],
            "method": "card",
        }
        signature = PaymentGatewayService._payment_signature(
            order["order_id"], payment_id
        )
        return PaymentGatewayService.verify_and_confirm_payment(
            booking=booking,
            order_id=order["order_id"],
            transaction_id=payment_id,
            signature=signature,
        )

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

        order = PaymentGatewayService.create_payment_order(booking1)
        confirmed = self._verify_payment(booking1, order, "TXN-999")
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)

        confirmed_again = self._verify_payment(booking1, order, "TXN-999")
        self.assertEqual(confirmed_again.status, Booking.Status.CONFIRMED)

        # Cancellation releases the seat back to AVAILABLE
        with patch("bookings.tasks.refund_booking.delay"):
            cancelled = confirmed.cancel_booking()
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.assertFalse(
            BookingSeat.objects.filter(booking=confirmed, is_active=True).exists()
        )
        self.show_seat_a1.refresh_from_db()
        self.assertEqual(self.show_seat_a1.status, ShowSeat.Status.AVAILABLE)
        confirmed.payment_attempts.get().refresh_from_db()
        self.assertEqual(
            confirmed.payment_attempts.get().status,
            PaymentAttempt.Status.REFUND_PENDING,
        )

    def test_pending_reservation_can_change_seats_before_payment(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        original_expiration = booking.expires_at
        updated = booking.update_pending_seats([self.show_seat_a2.id])

        self.assertEqual(
            list(
                updated.booking_seats.filter(is_active=True).values_list(
                    "show_seat_id", flat=True
                )
            ),
            [self.show_seat_a2.id],
        )
        self.assertEqual(updated.booking_seats.count(), 2)
        self.assertEqual(
            updated.booking_seats.filter(is_active=False).get().show_seat_id,
            self.show_seat_a1.id,
        )
        self.assertEqual(updated.expires_at, original_expiration)
        self.assertEqual(updated.subtotal_amount, Decimal("250.00"))
        self.show_seat_a1.refresh_from_db()
        self.show_seat_a2.refresh_from_db()
        self.assertEqual(self.show_seat_a1.status, ShowSeat.Status.AVAILABLE)
        self.assertEqual(self.show_seat_a2.status, ShowSeat.Status.HELD)

    def test_database_prevents_active_reservation_for_a_seat_twice(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        competing_booking = Booking.objects.create(
            user=self.user2,
            show=self.show,
            subtotal_amount=Decimal("250.00"),
            convenience_fee=Decimal("20.00"),
            total_amount=Decimal("270.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BookingSeat.objects.create(
                    booking=competing_booking,
                    show_seat=self.show_seat_a1,
                    price=Decimal("250.00"),
                )

        self.assertTrue(
            BookingSeat.objects.filter(booking=booking, is_active=True).exists()
        )

    def test_seats_cannot_change_after_payment_order_is_created(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        PaymentGatewayService.create_payment_order(booking)

        with self.assertRaises(ValidationError):
            booking.update_pending_seats([self.show_seat_a2.id])

    def test_invalid_payment_signature_does_not_confirm_booking(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        self.client.force_login(self.user1)

        response = self.client.post(
            reverse(
                "bookings:payment_callback",
                kwargs={"booking_reference": booking.booking_reference},
            ),
            {
                "razorpay_order_id": order["order_id"],
                "razorpay_payment_id": "pay-invalid-signature",
                "razorpay_signature": "invalid",
            },
        )

        booking.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)
        self.assertEqual(
            booking.payment_attempts.get().status, PaymentAttempt.Status.PENDING
        )

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
    def test_duplicate_capture_webhook_is_idempotent(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        payment_id = "pay-webhook-captured"
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_id,
                            "order_id": order["order_id"],
                            "amount": order["amount_paise"],
                            "currency": order["currency"],
                            "method": "card",
                        }
                    }
                },
            }
        ).encode()

        first_result = PaymentGatewayService.handle_webhook(
            body=body, signature="valid", event_id="event-captured-1"
        )
        duplicate_result = PaymentGatewayService.handle_webhook(
            body=body, signature="valid", event_id="event-captured-1"
        )

        booking.refresh_from_db()
        self.assertTrue(first_result)
        self.assertFalse(duplicate_result)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(booking.payment_transactions.count(), 1)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
    def test_failed_payment_webhook_records_failure_without_confirming(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        body = json.dumps(
            {
                "event": "payment.failed",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay-webhook-failed",
                            "order_id": order["order_id"],
                            "error_description": "Issuer declined the payment",
                        }
                    }
                },
            }
        ).encode()

        processed = PaymentGatewayService.handle_webhook(
            body=body, signature="valid", event_id="event-failed-1"
        )

        booking.refresh_from_db()
        attempt = booking.payment_attempts.get()
        self.assertTrue(processed)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(attempt.failure_reason, "Issuer declined the payment")

    def test_checkout_allows_pre_payment_seat_changes_then_creates_order_on_pay(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        self.client.force_login(self.user1)
        checkout_url = reverse(
            "bookings:checkout",
            kwargs={"booking_reference": booking.booking_reference},
        )
        response = self.client.get(checkout_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modify selected seats")
        self.assertEqual(booking.payment_attempts.count(), 0)

        change_seats_url = reverse(
            "bookings:seat_selection", kwargs={"show_id": self.show.pk}
        )
        response = self.client.get(
            change_seats_url, {"booking": booking.booking_reference}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Update Seats")
        self.client.post(
            f"{change_seats_url}?booking={booking.booking_reference}",
            {"seat_ids": str(self.show_seat_a2.pk)},
        )
        booking.refresh_from_db()
        self.assertEqual(
            list(
                booking.booking_seats.filter(is_active=True).values_list(
                    "show_seat_id", flat=True
                )
            ),
            [self.show_seat_a2.pk],
        )

        response = self.client.post(checkout_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currency"], "INR")
        self.assertEqual(booking.payment_attempts.count(), 1)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_checkout_reports_missing_razorpay_configuration_without_creating_order(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        self.client.force_login(self.user1)
        checkout_url = reverse(
            "bookings:checkout",
            kwargs={"booking_reference": booking.booking_reference},
        )

        with self.assertLogs("bookings.views", level="ERROR") as logs:
            response = self.client.post(checkout_url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"],
            "Online payments are temporarily unavailable.",
        )
        self.assertIn("RAZORPAY_KEY_ID", "\n".join(logs.output))
        self.assertIn("RAZORPAY_KEY_SECRET", "\n".join(logs.output))
        self.assertEqual(booking.payment_attempts.count(), 0)

    def test_gateway_order_failure_is_reported_without_recording_attempt(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        self.client.force_login(self.user1)
        checkout_url = reverse(
            "bookings:checkout",
            kwargs={"booking_reference": booking.booking_reference},
        )
        self.gateway_client.order.create.side_effect = RuntimeError(
            "upstream diagnostic that must not reach the user"
        )

        with self.assertLogs("bookings.payments", level="ERROR") as logs:
            response = self.client.post(checkout_url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["error"],
            "The payment provider could not start checkout. Please retry.",
        )
        self.assertNotIn("upstream diagnostic", response.content.decode())
        self.assertNotIn("upstream diagnostic", "\n".join(logs.output))
        self.assertEqual(booking.payment_attempts.count(), 0)

    def test_unresolved_payment_prevents_pending_booking_cancellation(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        PaymentGatewayService.create_payment_order(booking)

        with self.assertRaises(ValidationError):
            booking.cancel_booking()
        self.show_seat_a1.refresh_from_db()
        self.assertEqual(self.show_seat_a1.status, ShowSeat.Status.HELD)

    def test_failed_payment_can_be_retried_with_a_new_gateway_order(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        first_order = PaymentGatewayService.create_payment_order(booking)
        PaymentGatewayService.record_failed_payment(
            order_id=first_order["order_id"],
            payment_id="pay_failed_1",
            failure_reason="Issuer declined",
        )
        booking.refresh_from_db()
        self.assertTrue(booking.can_retry_payment)

        second_order = PaymentGatewayService.create_payment_order(booking, retry=True)
        self.assertNotEqual(first_order["order_id"], second_order["order_id"])
        self.assertEqual(booking.payment_attempts.count(), 2)

    def test_late_captured_payment_is_queued_for_refund_not_booking(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        booking.expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=["expires_at"])
        self.show_seat_a1.held_until = timezone.now() - timedelta(seconds=1)
        self.show_seat_a1.save(update_fields=["held_until"])
        with patch("bookings.payments.PaymentGatewayService._queue_late_payment_refund") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                result = PaymentGatewayService.confirm_captured_payment(
                    order_id=order["order_id"],
                    payment_id="pay_late_1",
                    amount=order["amount_paise"],
                    currency=order["currency"],
                )

        booking.refresh_from_db()
        self.assertEqual(result.status, Booking.Status.PENDING_PAYMENT)
        self.assertEqual(booking.payment_status, Booking.PaymentStatus.REFUND_PENDING)
        self.assertEqual(
            booking.payment_attempts.get().status,
            PaymentAttempt.Status.REFUND_PENDING,
        )
        queue.assert_called_once()

    def test_expired_reservation_releases_and_deactivates_seat_history(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        booking.expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=["expires_at"])
        self.show_seat_a1.held_until = timezone.now() - timedelta(seconds=1)
        self.show_seat_a1.save(update_fields=["held_until"])

        result = PaymentGatewayService.reconcile_expired_booking(booking.pk)

        booking.refresh_from_db()
        self.show_seat_a1.refresh_from_db()
        self.assertEqual(result, "expired")
        self.assertEqual(booking.status, Booking.Status.EXPIRED)
        self.assertEqual(self.show_seat_a1.status, ShowSeat.Status.AVAILABLE)
        self.assertFalse(
            BookingSeat.objects.filter(booking=booking, is_active=True).exists()
        )

    def test_refund_completion_is_recorded_and_repeat_calls_are_idempotent(self):
        booking = self._confirm_booking()
        with patch("bookings.tasks.refund_booking.delay"):
            booking.cancel_booking()
        attempt = booking.payment_attempts.get()

        self.assertTrue(PaymentGatewayService.process_refund(attempt.pk))
        self.assertTrue(PaymentGatewayService.process_refund(attempt.pk))
        attempt.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertIsNotNone(attempt.refunded_at)
        self.assertEqual(booking.payment_status, Booking.PaymentStatus.REFUNDED)
        self.gateway_client.payment.refund.assert_called_once()

    def _confirm_booking(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        return self._verify_payment(booking, order, "TXN-TICKET-1")

    def test_confirmation_queues_ticket_email_after_commit(self):
        booking = Booking.create_pending_booking(
            user=self.user1,
            show=self.show,
            show_seat_ids=[self.show_seat_a1.id],
        )
        order = PaymentGatewayService.create_payment_order(booking)
        with patch("bookings.tasks.send_booking_ticket_email.delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self._verify_payment(booking, order, "TXN-TICKET-2")
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

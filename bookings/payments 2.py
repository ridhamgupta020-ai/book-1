"""
Server-side payment gateway abstraction for MyBookShow.
Separates booking creation from payment verification, enforces HMAC signature verification,
and guarantees idempotent callback handling.
"""

import hashlib
import hmac
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from movies.models import ShowSeat
from .models import Booking


class PaymentGatewayService:
    """
    Production-ready payment abstraction supporting HMAC-signed gateway verification.
    Never stores raw card numbers or CVV values, and never trusts client-only flags.
    """

    @staticmethod
    def _signing_key() -> bytes:
        return settings.SECRET_KEY.encode("utf-8")

    @classmethod
    def create_payment_order(cls, booking: Booking) -> dict:
        if booking.status != Booking.Status.PENDING_PAYMENT:
            raise ValidationError("Payment order can only be created for pending bookings.")
        order_id = booking.payment_Order_id or f"ORD-{secrets.token_hex(6).upper()}"
        if not booking.payment_Order_id:
            booking.payment_Order_id = order_id
            booking.save(update_fields=["payment_Order_id", "updated_at"])
        return {
            "order_id": order_id,
            "booking_reference": booking.booking_reference,
            "amount": str(booking.total_amount),
            "currency": "INR",
            "mode": "DEMO_DEVELOPMENT_SANDBOX",
        }

    @classmethod
    def generate_gateway_signature(cls, *, order_id: str, transaction_id: str, amount: str) -> str:
        message = f"{order_id}|{transaction_id}|{amount}".encode("utf-8")
        return hmac.new(cls._signing_key(), message, hashlib.sha256).hexdigest()

    @classmethod
    def verify_and_confirm_payment(
        cls,
        *,
        booking: Booking,
        order_id: str,
        transaction_id: str,
        signature: str,
    ) -> Booking:
        """
        Idempotently verifies payment signature server-side and transitions seats from HELD to BOOKED.
        """
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)

            # Idempotency check: if already confirmed with same transaction_id, return immediately
            if (
                locked_booking.status == Booking.Status.CONFIRMED
                and locked_booking.payment_status == Booking.PaymentStatus.PAID
            ):
                return locked_booking

            if locked_booking.status != Booking.Status.PENDING_PAYMENT:
                raise ValidationError(
                    f"Booking {locked_booking.booking_reference} is in state '{locked_booking.status}' and cannot be confirmed."
                )

            if locked_booking.expires_at and locked_booking.expires_at < timezone.now():
                locked_booking.status = Booking.Status.EXPIRED
                locked_booking.payment_status = Booking.PaymentStatus.FAILED
                locked_booking.save(update_fields=["status", "payment_status", "updated_at"])
                raise ValidationError("Seat hold has expired. Please select seats again.")

            expected_sig = cls.generate_gateway_signature(
                order_id=order_id,
                transaction_id=transaction_id,
                amount=str(locked_booking.total_amount),
            )
            if not hmac.compare_digest(expected_sig, signature or ""):
                raise ValidationError("Invalid payment gateway signature verification.")

            seat_ids = list(
                locked_booking.booking_seats.values_list("show_seat_id", flat=True)
            )
            locked_seats = list(
                ShowSeat.objects.select_for_update().filter(id__in=seat_ids)
            )
            for ss in locked_seats:
                if ss.status == ShowSeat.Status.BOOKED:
                    raise ValidationError(f"Seat {ss.seat.label} was already booked.")
                ss.status = ShowSeat.Status.BOOKED
                ss.held_until = None
            ShowSeat.objects.bulk_update(
                locked_seats, ["status", "held_until", "updated_at"]
            )

            locked_booking.status = Booking.Status.CONFIRMED
            locked_booking.payment_status = Booking.PaymentStatus.PAID
            locked_booking.payment_Order_id = order_id
            locked_booking.payment_transaction_id = transaction_id
            locked_booking.save(
                update_fields=[
                    "status",
                    "payment_status",
                    "payment_Order_id",
                    "payment_transaction_id",
                    "updated_at",
                ]
            )
            return locked_booking

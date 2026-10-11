import hashlib
import hmac
import json
import logging
import secrets
from decimal import Decimal

import razorpay
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from movies.models import ShowSeat

from .models import (
    Booking,
    GatewayWebhookEvent,
    PaymentAttempt,
    PaymentTransaction,
)

logger = logging.getLogger(__name__)


class PaymentGatewayUnavailable(Exception):
    pass


class PaymentGatewayService:
    @staticmethod
    def _client():
        missing_settings = [
            name
            for name, value in (
                ("RAZORPAY_KEY_ID", settings.RAZORPAY_KEY_ID),
                ("RAZORPAY_KEY_SECRET", settings.RAZORPAY_KEY_SECRET),
            )
            if not value.strip()
        ]
        if missing_settings:
            raise ImproperlyConfigured(
                "Missing required Razorpay configuration: "
                + ", ".join(missing_settings)
                + "."
            )
        return razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    @classmethod
    def create_payment_order(cls, booking: Booking, *, retry: bool = False) -> dict:
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked_booking.status != Booking.Status.PENDING_PAYMENT:
                raise ValidationError("Payment is only available for pending bookings.")
            if not locked_booking.expires_at or locked_booking.expires_at <= timezone.now():
                raise ValidationError("The seat reservation has expired. Please select seats again.")

            active_attempt = (
                PaymentAttempt.objects.select_for_update()
                .filter(booking=locked_booking, status=PaymentAttempt.Status.PENDING)
                .first()
            )
            if active_attempt and not retry:
                return {
                    **cls._public_order_details(active_attempt),
                    "key_id": settings.RAZORPAY_KEY_ID,
                }
            if active_attempt:
                raise ValidationError("A payment attempt is already being processed.")

            if retry:
                latest_attempt = locked_booking.payment_attempts.order_by(
                    "-created_at"
                ).first()
                if latest_attempt and latest_attempt.status not in {
                    PaymentAttempt.Status.FAILED,
                    PaymentAttempt.Status.CANCELLED,
                }:
                    raise ValidationError("This payment cannot be retried yet.")

            seats = list(
                ShowSeat.objects.select_for_update()
                .filter(
                    booking_entries__booking=locked_booking,
                    booking_entries__is_active=True,
                )
                .order_by("id")
            )
            now = timezone.now()
            if not seats or any(
                seat.status != ShowSeat.Status.HELD
                or seat.held_by_id != locked_booking.user_id
                or not seat.held_until
                or seat.held_until <= now
                for seat in seats
            ):
                raise ValidationError("The selected seats are no longer reserved.")

            try:
                order = cls._client().order.create(
                    data={
                        "amount": int(locked_booking.total_amount * 100),
                        "currency": "INR",
                        "receipt": locked_booking.booking_reference,
                        "notes": {
                            "booking_reference": locked_booking.booking_reference,
                            "user_id": str(locked_booking.user_id),
                        },
                    }
                )
            except ImproperlyConfigured:
                raise
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if not isinstance(status_code, int):
                    status_code = "unknown"
                logger.error(
                    "Razorpay order creation failed (error_type=%s, status_code=%s).",
                    type(exc).__name__,
                    status_code,
                )
                raise PaymentGatewayUnavailable(
                    "The payment provider could not start checkout. Please retry."
                ) from exc
            if (
                order.get("currency") != "INR"
                or order.get("amount") != int(locked_booking.total_amount * 100)
                or not order.get("id")
            ):
                raise ValidationError("The payment provider returned an invalid order.")
            attempt = PaymentAttempt.objects.create(
                booking=locked_booking,
                gateway_order_id=order["id"],
                amount=locked_booking.total_amount,
            )
            locked_booking.payment_Order_id = order["id"]
            locked_booking.save(update_fields=["payment_Order_id", "updated_at"])
            return {
                **cls._public_order_details(attempt),
                "key_id": settings.RAZORPAY_KEY_ID,
            }

    @staticmethod
    def _public_order_details(attempt: PaymentAttempt) -> dict:
        return {
            "order_id": attempt.gateway_order_id,
            "booking_reference": attempt.booking.booking_reference,
            "amount": str(attempt.amount),
            "amount_paise": int(attempt.amount * 100),
            "currency": attempt.currency,
            "status": attempt.status,
        }

    @staticmethod
    def _payment_signature(order_id: str, payment_id: str) -> str:
        message = f"{order_id}|{payment_id}".encode("utf-8")
        return hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def verify_and_confirm_payment(
        cls,
        *,
        booking: Booking,
        order_id: str,
        transaction_id: str,
        signature: str,
    ) -> Booking:
        expected_signature = cls._payment_signature(order_id, transaction_id)
        if not hmac.compare_digest(expected_signature, signature or ""):
            raise ValidationError("Invalid payment gateway signature.")

        attempt = PaymentAttempt.objects.filter(
            booking=booking, gateway_order_id=order_id
        ).first()
        if attempt is None:
            raise ValidationError("Payment order does not belong to this booking.")
        payment = cls._client().payment.fetch(transaction_id)
        if (
            payment.get("order_id") != order_id
            or payment.get("status") != "captured"
            or payment.get("currency") != attempt.currency
            or payment.get("amount") != int(attempt.amount * 100)
        ):
            raise ValidationError("The payment could not be verified as captured.")
        cls.confirm_captured_payment(
            order_id=order_id,
            payment_id=transaction_id,
            payment_method=payment.get("method", ""),
        )
        booking.refresh_from_db()
        return booking

    @classmethod
    def handle_webhook(cls, *, body: bytes, signature: str, event_id: str) -> bool:
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            raise ImproperlyConfigured("RAZORPAY_WEBHOOK_SECRET is not configured.")
        try:
            cls._client().utility.verify_webhook_signature(
                body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
            )
        except (razorpay.errors.SignatureVerificationError, UnicodeDecodeError) as exc:
            raise ValidationError("Invalid Razorpay webhook signature.") from exc

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError("Malformed webhook payload.") from exc

        event_type = payload.get("event", "")
        if event_type not in {"payment.captured", "payment.failed"}:
            return False
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment.get("order_id")
        payment_id = payment.get("id")
        if not event_id or not order_id or not payment_id:
            raise ValidationError("Webhook is missing its event or payment identifiers.")

        try:
            with transaction.atomic():
                event = GatewayWebhookEvent.objects.create(
                    event_id=event_id, event_type=event_type
                )
        except IntegrityError:
            return False

        try:
            if event_type == "payment.captured":
                cls.confirm_captured_payment(
                    order_id=order_id,
                    payment_id=payment_id,
                    payment_method=payment.get("method", ""),
                    amount=payment.get("amount"),
                    currency=payment.get("currency"),
                )
            else:
                cls.record_failed_payment(
                    order_id=order_id,
                    payment_id=payment_id,
                    failure_reason=payment.get("error_description", "Payment failed"),
                )
        except Exception:
            event.delete()
            raise
        GatewayWebhookEvent.objects.filter(pk=event.pk).update(
            processed_at=timezone.now()
        )
        return True

    @classmethod
    def confirm_captured_payment(
        cls,
        *,
        order_id: str,
        payment_id: str,
        payment_method: str = "",
        amount: int | None = None,
        currency: str | None = None,
    ) -> Booking:
        with transaction.atomic():
            attempt = (
                PaymentAttempt.objects.select_for_update()
                .select_related("booking")
                .get(gateway_order_id=order_id)
            )
            booking = Booking.objects.select_for_update().get(pk=attempt.booking_id)
            if amount is not None and amount != int(attempt.amount * 100):
                raise ValidationError("Captured amount does not match the payment order.")
            if currency is not None and currency != attempt.currency:
                raise ValidationError("Captured currency does not match the payment order.")
            if attempt.status == PaymentAttempt.Status.SUCCESS:
                if attempt.gateway_payment_id != payment_id:
                    raise ValidationError("This order was captured with a different payment.")
                return booking
            if attempt.status not in {
                PaymentAttempt.Status.PENDING,
                PaymentAttempt.Status.FAILED,
            }:
                raise ValidationError("This payment attempt is not pending.")

            seats = list(
                ShowSeat.objects.select_for_update()
                .filter(
                    booking_entries__booking=booking,
                    booking_entries__is_active=True,
                )
                .order_by("id")
            )
            reservation_is_valid = (
                booking.status == Booking.Status.PENDING_PAYMENT
                and booking.expires_at is not None
                and booking.expires_at > timezone.now()
                and bool(seats)
                and all(
                    seat.status == ShowSeat.Status.HELD
                    and seat.held_by_id == booking.user_id
                    and seat.held_until
                    and seat.held_until > timezone.now()
                    for seat in seats
                )
            )
            attempt.gateway_payment_id = payment_id
            attempt.payment_method = payment_method or ""
            payment_transaction, created = PaymentTransaction.objects.get_or_create(
                gateway_payment_id=payment_id,
                defaults={
                    "attempt": attempt,
                    "booking": booking,
                    "amount": attempt.amount,
                    "currency": attempt.currency,
                    "status": PaymentAttempt.Status.SUCCESS,
                    "payment_method": payment_method or "",
                },
            )
            if not created and (
                payment_transaction.attempt_id != attempt.pk
                or payment_transaction.booking_id != booking.pk
            ):
                raise ValidationError("Payment identifier is associated with another order.")
            if not reservation_is_valid:
                attempt.status = PaymentAttempt.Status.REFUND_PENDING
                payment_transaction.status = PaymentAttempt.Status.REFUND_PENDING
                payment_transaction.save(update_fields=["status", "updated_at"])
                attempt.save(
                    update_fields=[
                        "gateway_payment_id",
                        "payment_method",
                        "status",
                        "updated_at",
                    ]
                )
                booking.payment_status = Booking.PaymentStatus.REFUND_PENDING
                booking.save(update_fields=["payment_status", "updated_at"])
                transaction.on_commit(
                    lambda attempt_id=attempt.pk: cls._queue_late_payment_refund(
                        attempt_id
                    ),
                    robust=True,
                )
                return booking

            for seat in seats:
                seat.status = ShowSeat.Status.BOOKED
                seat.held_until = None
            ShowSeat.objects.bulk_update(
                seats, ["status", "held_until", "updated_at"]
            )
            attempt.status = PaymentAttempt.Status.SUCCESS
            payment_transaction.status = PaymentAttempt.Status.SUCCESS
            payment_transaction.save(update_fields=["status", "updated_at"])
            attempt.save(
                update_fields=[
                    "gateway_payment_id",
                    "payment_method",
                    "status",
                    "updated_at",
                ]
            )
            booking.status = Booking.Status.CONFIRMED
            booking.payment_status = Booking.PaymentStatus.PAID
            booking.payment_Order_id = order_id
            booking.payment_transaction_id = payment_id
            booking.save(
                update_fields=[
                    "status",
                    "payment_status",
                    "payment_Order_id",
                    "payment_transaction_id",
                    "updated_at",
                ]
            )
            transaction.on_commit(
                lambda booking_id=booking.pk: cls._queue_ticket_email(booking_id),
                robust=True,
            )
            return booking

    @classmethod
    def record_failed_payment(
        cls, *, order_id: str, payment_id: str, failure_reason: str
    ) -> None:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.select_for_update().get(
                gateway_order_id=order_id
            )
            if attempt.status != PaymentAttempt.Status.PENDING:
                return
            attempt.gateway_payment_id = payment_id
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.failure_reason = failure_reason[:255]
            attempt.save(
                update_fields=[
                    "gateway_payment_id",
                    "status",
                    "failure_reason",
                    "updated_at",
                ]
            )
            payment_transaction, created = PaymentTransaction.objects.get_or_create(
                gateway_payment_id=payment_id,
                defaults={
                    "attempt": attempt,
                    "booking_id": attempt.booking_id,
                    "amount": attempt.amount,
                    "currency": attempt.currency,
                    "status": PaymentAttempt.Status.FAILED,
                    "failure_reason": failure_reason[:255],
                },
            )
            if not created:
                if (
                    payment_transaction.attempt_id != attempt.pk
                    or payment_transaction.booking_id != attempt.booking_id
                ):
                    raise ValidationError(
                        "Payment identifier is associated with another order."
                    )
                payment_transaction.status = PaymentAttempt.Status.FAILED
                payment_transaction.failure_reason = failure_reason[:255]
                payment_transaction.save(
                    update_fields=["status", "failure_reason", "updated_at"]
                )
            booking = Booking.objects.select_for_update().get(pk=attempt.booking_id)
            booking.payment_status = Booking.PaymentStatus.FAILED
            booking.save(update_fields=["payment_status", "updated_at"])

    @classmethod
    def reconcile_expired_booking(cls, booking_id: int) -> str:
        booking = Booking.objects.get(pk=booking_id)
        if (
            booking.status != Booking.Status.PENDING_PAYMENT
            or not booking.expires_at
            or booking.expires_at > timezone.now()
        ):
            return "not_expired"
        pending_attempts = list(
            PaymentAttempt.objects.filter(
                booking=booking, status=PaymentAttempt.Status.PENDING
            )
        )
        for attempt in pending_attempts:
            payments = cls._client().order.payments(attempt.gateway_order_id).get(
                "items", []
            )
            captured = next(
                (payment for payment in payments if payment.get("status") == "captured"),
                None,
            )
            if captured:
                cls.confirm_captured_payment(
                    order_id=attempt.gateway_order_id,
                    payment_id=captured["id"],
                    payment_method=captured.get("method", ""),
                    amount=captured.get("amount"),
                    currency=captured.get("currency"),
                )
                return "captured"
            unresolved = [
                payment
                for payment in payments
                if payment.get("status") not in {"failed", "refunded"}
            ]
            if unresolved or not payments:
                return "payment_pending"
            for payment in payments:
                if payment.get("status") == "failed":
                    cls.record_failed_payment(
                        order_id=attempt.gateway_order_id,
                        payment_id=payment["id"],
                        failure_reason=payment.get(
                            "error_description", "Payment failed"
                        ),
                    )

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking_id)
            if (
                booking.status != Booking.Status.PENDING_PAYMENT
                or not booking.expires_at
                or booking.expires_at > timezone.now()
            ):
                return "not_expired"
            pending_attempts = list(
                PaymentAttempt.objects.select_for_update().filter(
                    booking=booking, status=PaymentAttempt.Status.PENDING
                )
            )
            if pending_attempts:
                return "payment_pending"
            seats = list(
                ShowSeat.objects.select_for_update()
                .filter(
                    booking_entries__booking=booking,
                    booking_entries__is_active=True,
                )
                .order_by("id")
            )
            for seat in seats:
                if (
                    seat.status == ShowSeat.Status.HELD
                    and seat.held_by_id == booking.user_id
                    and seat.held_until
                    and seat.held_until <= timezone.now()
                ):
                    seat.status = ShowSeat.Status.AVAILABLE
                    seat.held_by = None
                    seat.held_until = None
            ShowSeat.objects.bulk_update(
                seats, ["status", "held_by", "held_until", "updated_at"]
            )
            booking.booking_seats.filter(is_active=True).update(is_active=False)
            booking.status = Booking.Status.EXPIRED
            if booking.payment_status == Booking.PaymentStatus.PENDING:
                booking.payment_status = Booking.PaymentStatus.CANCELLED
            booking.save(update_fields=["status", "payment_status", "updated_at"])
            return "expired"

    @classmethod
    def process_refund(cls, attempt_id: int) -> bool:
        with transaction.atomic():
            attempt = (
                PaymentAttempt.objects.select_for_update()
                .select_related("booking")
                .get(pk=attempt_id)
            )
            if attempt.status == PaymentAttempt.Status.REFUNDED:
                return True
            if attempt.status not in {
                PaymentAttempt.Status.SUCCESS,
                PaymentAttempt.Status.REFUND_PENDING,
                PaymentAttempt.Status.PARTIALLY_REFUNDED,
            }:
                raise ValidationError("This payment attempt is not eligible for refund.")

            client = cls._client()
            if attempt.refund_reference:
                refund = client.refund.fetch(attempt.refund_reference)
            else:
                if not attempt.gateway_payment_id:
                    raise ValidationError(
                        "Cannot refund an attempt without a captured payment."
                    )
                refund = client.payment.refund(
                    attempt.gateway_payment_id,
                    {
                        "amount": int(
                            (attempt.amount - attempt.refunded_amount) * 100
                        ),
                        "notes": {
                            "booking_reference": attempt.booking.booking_reference,
                            "payment_attempt": str(attempt.pk),
                        },
                    },
                )
                attempt.refund_reference = refund.get("id", "")

            status = refund.get("status")
            if status == "processed":
                attempt.refunded_amount += Decimal(refund.get("amount", 0)) / 100
                is_fully_refunded = attempt.refunded_amount >= attempt.amount
                attempt.status = (
                    PaymentAttempt.Status.REFUNDED
                    if is_fully_refunded
                    else PaymentAttempt.Status.PARTIALLY_REFUNDED
                )
                attempt.refunded_at = timezone.now()
                attempt.save(
                    update_fields=[
                        "status",
                        "refund_reference",
                        "refunded_amount",
                        "refunded_at",
                        "updated_at",
                    ]
                )
                PaymentTransaction.objects.filter(
                    attempt=attempt,
                    gateway_payment_id=attempt.gateway_payment_id,
                ).update(status=attempt.status)
                Booking.objects.filter(pk=attempt.booking_id).update(
                    payment_status=(
                        Booking.PaymentStatus.REFUNDED
                        if is_fully_refunded
                        else Booking.PaymentStatus.PARTIALLY_REFUNDED
                    ),
                    updated_at=timezone.now(),
                )
                return True
            if status in {"failed", "rejected"}:
                attempt.failure_reason = f"Refund {status}"[:255]
                attempt.save(
                    update_fields=["refund_reference", "failure_reason", "updated_at"]
                )
                return False
            attempt.save(update_fields=["refund_reference", "updated_at"])
            return False

    @staticmethod
    def _queue_ticket_email(booking_id: int) -> None:
        from .tasks import send_booking_ticket_email

        try:
            send_booking_ticket_email.delay(booking_id)
        except Exception:
            logger.exception(
                "Could not queue ticket email for booking %s.", booking_id
            )

    @staticmethod
    def _queue_late_payment_refund(attempt_id: int) -> None:
        from .tasks import refund_late_payment

        try:
            refund_late_payment.delay(attempt_id)
        except Exception:
            logger.exception(
                "Could not queue a refund for late payment attempt %s.", attempt_id
            )

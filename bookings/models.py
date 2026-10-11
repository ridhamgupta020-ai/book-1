import base64
import io
import secrets
from datetime import timedelta
from decimal import Decimal
import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from movies.models import Show, ShowSeat

SEAT_HOLD_DURATION_MINUTES = 2
CONVENIENCE_FEE_RATE = Decimal("0.08")  # 8% convenience fee


def generate_booking_reference() -> str:
    return f"MBS-{secrets.token_hex(4).upper()}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUND_PENDING = "refund_pending", "Refund Pending"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
        REFUNDED = "refunded", "Refunded"

    booking_reference = models.CharField(
        max_length=24, unique=True, default=generate_booking_reference, db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    show = models.ForeignKey(
        Show, on_delete=models.PROTECT, related_name="bookings"
    )
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    convenience_fee = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    payment_Order_id = models.CharField(max_length=120, blank=True, default="")
    payment_transaction_id = models.CharField(max_length=120, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["payment_status", "created_at"]),
            models.Index(fields=["expires_at", "status"]),
            models.Index(fields=["cancelled_at"]),
        ]

    @property
    def is_cancellable(self) -> bool:
        """Documented policy: Bookings can be cancelled up to 2 hours before showtime."""
        if self.status not in {self.Status.PENDING_PAYMENT, self.Status.CONFIRMED}:
            return False
        cutoff = self.show.start_time - timedelta(hours=2)
        return timezone.now() < cutoff

    @property
    def latest_payment_attempt(self):
        attempts = self.payment_attempts.all()
        return attempts[0] if attempts else None

    @property
    def can_retry_payment(self) -> bool:
        attempt = self.latest_payment_attempt
        return bool(
            self.status == self.Status.PENDING_PAYMENT
            and self.expires_at
            and self.expires_at > timezone.now()
            and attempt
            and attempt.status
            in {PaymentAttempt.Status.FAILED, PaymentAttempt.Status.CANCELLED}
        )

    @property
    def can_modify_seats(self) -> bool:
        return bool(
            self.status == self.Status.PENDING_PAYMENT
            and self.expires_at
            and self.expires_at > timezone.now()
            and not self.payment_attempts.exists()
        )

    def generate_qr_code_data_uri(self) -> str:
        seat_labels = ", ".join(
            bs.show_seat.seat.label
            for bs in self.booking_seats.filter(is_active=True).select_related(
                "show_seat__seat"
            )
        )
        payload = (
            f"MYBOOKSHOW|REF:{self.booking_reference}|MOVIE:{self.show.movie.title}|"
            f"SHOW:{self.show.start_time:%Y-%m-%d %H:%M}|SEATS:{seat_labels}|STATUS:{self.status}"
        )
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @classmethod
    def create_pending_booking(cls, *, user, show: Show, show_seat_ids: list[int]):
        """
        Atomically locks requested ShowSeat rows using PostgreSQL SELECT ... FOR UPDATE,
        releases expired holds, prevents double booking, and creates a pending Booking.
        """
        if not show_seat_ids:
            raise ValidationError("Please select at least one seat.")
        if len(show_seat_ids) > 10:
            raise ValidationError("A maximum of 10 seats can be booked per transaction.")

        now = timezone.now()
        if show.start_time <= now:
            raise ValidationError("Bookings are closed for shows that have already started.")
        if len(show_seat_ids) != len(set(show_seat_ids)):
            raise ValidationError("Each seat may only be selected once.")

        with transaction.atomic():
            locked_seats = list(
                ShowSeat.objects.select_for_update()
                .select_related("seat")
                .filter(show=show, id__in=show_seat_ids)
                .order_by("id")
            )
            if len(locked_seats) != len(set(show_seat_ids)):
                raise ValidationError("One or more selected seats do not belong to this show.")

            subtotal = Decimal("0.00")
            for ss in locked_seats:
                # Release expired temporary hold automatically
                if (
                    ss.status == ShowSeat.Status.HELD
                    and ss.held_until
                    and ss.held_until <= now
                ):
                    ss.status = ShowSeat.Status.AVAILABLE
                    ss.held_by = None
                    ss.held_until = None

                if ss.status == ShowSeat.Status.BOOKED:
                    raise ValidationError(
                        f"Seat {ss.seat.label} has already been booked."
                    )
                if (
                    ss.status == ShowSeat.Status.HELD
                    and ss.held_by_id == user.id
                ):
                    raise ValidationError(
                        "You already have an active reservation for one or more selected seats."
                    )
                if ss.status == ShowSeat.Status.HELD and ss.held_by_id != user.id:
                    raise ValidationError(
                        f"Seat {ss.seat.label} is temporarily held by another customer."
                    )
                subtotal += ss.effective_price

            hold_expiry = now + timedelta(minutes=SEAT_HOLD_DURATION_MINUTES)
            for ss in locked_seats:
                ss.status = ShowSeat.Status.HELD
                ss.held_by = user
                ss.held_until = hold_expiry
            ShowSeat.objects.bulk_update(
                locked_seats, ["status", "held_by", "held_until", "updated_at"]
            )

            convenience_fee = (subtotal * CONVENIENCE_FEE_RATE).quantize(Decimal("0.01"))
            total_amount = (subtotal + convenience_fee).quantize(Decimal("0.01"))

            booking = cls.objects.create(
                user=user,
                show=show,
                subtotal_amount=subtotal,
                convenience_fee=convenience_fee,
                total_amount=total_amount,
                status=cls.Status.PENDING_PAYMENT,
                payment_status=cls.PaymentStatus.PENDING,
                expires_at=hold_expiry,
            )

            BookingSeat.objects.bulk_create(
                [
                    BookingSeat(
                        booking=booking,
                        show_seat=ss,
                        price=ss.effective_price,
                    )
                    for ss in locked_seats
                ]
            )
            return booking

    def update_pending_seats(self, show_seat_ids: list[int]):
        if not show_seat_ids:
            raise ValidationError("Please select at least one seat.")
        if len(show_seat_ids) > 10:
            raise ValidationError("A maximum of 10 seats can be booked per transaction.")
        if len(show_seat_ids) != len(set(show_seat_ids)):
            raise ValidationError("Each seat may only be selected once.")

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=self.pk)
            now = timezone.now()
            if (
                booking.status != self.Status.PENDING_PAYMENT
                or not booking.expires_at
                or booking.expires_at <= now
                or booking.show.start_time <= now
            ):
                raise ValidationError("This seat reservation is no longer active.")
            if booking.payment_attempts.exists():
                raise ValidationError(
                    "Seats cannot be changed after payment has been initiated."
                )

            all_entries = list(
                booking.booking_seats.select_for_update().select_related("show_seat")
            )
            active_entries = [entry for entry in all_entries if entry.is_active]
            existing_ids = {entry.show_seat_id for entry in active_entries}
            requested_ids = set(show_seat_ids)
            seats = list(
                ShowSeat.objects.select_for_update()
                .select_related("seat")
                .filter(show=booking.show, id__in=existing_ids | requested_ids)
                .order_by("id")
            )
            seat_by_id = {seat.pk: seat for seat in seats}
            if not requested_ids.issubset(seat_by_id):
                raise ValidationError("One or more selected seats do not belong to this show.")

            selected_seats = [seat_by_id[seat_id] for seat_id in show_seat_ids]
            for seat in selected_seats:
                if seat.pk in existing_ids:
                    if (
                        seat.status != ShowSeat.Status.HELD
                        or seat.held_by_id != booking.user_id
                        or not seat.held_until
                        or seat.held_until <= now
                    ):
                        raise ValidationError(
                            f"Your reservation for seat {seat.seat.label} has expired."
                        )
                elif seat.status != ShowSeat.Status.AVAILABLE:
                    raise ValidationError(
                        f"Seat {seat.seat.label} is no longer available."
                    )

            for seat_id in existing_ids - requested_ids:
                seat = seat_by_id[seat_id]
                if (
                    seat.status == ShowSeat.Status.HELD
                    and seat.held_by_id == booking.user_id
                ):
                    seat.status = ShowSeat.Status.AVAILABLE
                    seat.held_by = None
                    seat.held_until = None
                    seat.updated_at = now

            for seat in selected_seats:
                seat.status = ShowSeat.Status.HELD
                seat.held_by_id = booking.user_id
                seat.held_until = booking.expires_at
                seat.updated_at = now
            ShowSeat.objects.bulk_update(
                seats, ["status", "held_by", "held_until", "updated_at"]
            )

            existing_by_id = {entry.show_seat_id: entry for entry in all_entries}
            entries_to_create = []
            entries_to_update = []
            subtotal = Decimal("0.00")
            for seat in selected_seats:
                subtotal += seat.effective_price
                entry = existing_by_id.get(seat.pk)
                if entry is None:
                    entries_to_create.append(
                        BookingSeat(
                            booking=booking,
                            show_seat=seat,
                            price=seat.effective_price,
                        )
                    )
                else:
                    entry.price = seat.effective_price
                    entry.is_active = True
                    entries_to_update.append(entry)

            for entry in active_entries:
                if entry.show_seat_id not in requested_ids:
                    entry.is_active = False
                    entries_to_update.append(entry)
            if entries_to_create:
                BookingSeat.objects.bulk_create(entries_to_create)
            if entries_to_update:
                BookingSeat.objects.bulk_update(
                    entries_to_update, ["price", "is_active"]
                )

            booking.subtotal_amount = subtotal
            booking.convenience_fee = (subtotal * CONVENIENCE_FEE_RATE).quantize(
                Decimal("0.01")
            )
            booking.total_amount = booking.subtotal_amount + booking.convenience_fee
            booking.save(
                update_fields=[
                    "subtotal_amount",
                    "convenience_fee",
                    "total_amount",
                    "updated_at",
                ]
            )
            return booking

    def cancel_booking(self):
        """Atomically cancels a booking and releases its ShowSeat rows."""
        if not self.is_cancellable:
            raise ValidationError(
                "This booking cannot be cancelled (cancellations close 2 hours prior to showtime)."
            )
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=self.pk)
            if locked_booking.status == self.Status.CANCELLED:
                return locked_booking
            if (
                locked_booking.status == self.Status.PENDING_PAYMENT
                and locked_booking.payment_attempts.filter(
                    status=PaymentAttempt.Status.PENDING
                ).exists()
            ):
                raise ValidationError(
                    "Cancellation is unavailable while a payment is being processed."
                )

            seat_ids = list(
                locked_booking.booking_seats.filter(is_active=True).values_list(
                    "show_seat_id", flat=True
                )
            )
            locked_show_seats = list(
                ShowSeat.objects.select_for_update().filter(id__in=seat_ids)
            )
            for ss in locked_show_seats:
                ss.status = ShowSeat.Status.AVAILABLE
                ss.held_by = None
                ss.held_until = None
            ShowSeat.objects.bulk_update(
                locked_show_seats, ["status", "held_by", "held_until", "updated_at"]
            )
            locked_booking.booking_seats.filter(is_active=True).update(is_active=False)

            was_paid = locked_booking.payment_status == self.PaymentStatus.PAID
            locked_booking.status = self.Status.CANCELLED
            locked_booking.cancelled_at = timezone.now()
            locked_booking.payment_status = (
                self.PaymentStatus.REFUND_PENDING
                if was_paid
                else self.PaymentStatus.CANCELLED
            )
            locked_booking.save(
                update_fields=["status", "payment_status", "cancelled_at", "updated_at"]
            )
            if was_paid:
                locked_booking.payment_attempts.filter(
                    status=PaymentAttempt.Status.SUCCESS
                ).update(
                    status=PaymentAttempt.Status.REFUND_PENDING,
                    updated_at=timezone.now(),
                )
                transaction.on_commit(
                    lambda booking_id=locked_booking.pk: self._queue_refund(booking_id),
                    robust=True,
                )
            return locked_booking

    @staticmethod
    def _queue_refund(booking_id: int) -> None:
        from .tasks import refund_booking

        refund_booking.delay(booking_id)

    def __str__(self):
        return f"{self.booking_reference} ({self.user.username})"


class PaymentAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUND_PENDING = "refund_pending", "Refund Pending"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"

    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="payment_attempts"
    )
    gateway = models.CharField(max_length=24, default="razorpay")
    gateway_order_id = models.CharField(max_length=120, unique=True)
    gateway_payment_id = models.CharField(
        max_length=120, unique=True, null=True, blank=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    payment_method = models.CharField(max_length=32, blank=True, default="")
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    refund_reference = models.CharField(max_length=120, blank=True, default="")
    refunded_at = models.DateTimeField(null=True, blank=True)
    refunded_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["refunded_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_attempt_amount_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(refunded_amount__gte=0),
                name="payment_refunded_amount_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.gateway_order_id} ({self.get_status_display()})"


class GatewayWebhookEvent(models.Model):
    event_id = models.CharField(max_length=120, unique=True)
    event_type = models.CharField(max_length=80)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PaymentTransaction(models.Model):
    attempt = models.ForeignKey(
        PaymentAttempt, on_delete=models.PROTECT, related_name="transactions"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="payment_transactions"
    )
    gateway_payment_id = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=24)
    payment_method = models.CharField(max_length=32, blank=True, default="")
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class BookingSeat(models.Model):
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="booking_seats"
    )
    show_seat = models.ForeignKey(
        ShowSeat, on_delete=models.PROTECT, related_name="booking_entries"
    )
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "show_seat"], name="unique_show_seat_per_booking"
            ),
            models.UniqueConstraint(
                fields=["show_seat"],
                condition=models.Q(is_active=True),
                name="one_active_booking_per_show_seat",
            ),
        ]

    def __str__(self):
        return f"{self.booking.booking_reference} -> {self.show_seat.seat.label}"

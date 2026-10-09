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

SEAT_HOLD_DURATION_MINUTES = 10
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_cancellable(self) -> bool:
        """Documented policy: Bookings can be cancelled up to 2 hours before showtime."""
        if self.status not in {self.Status.PENDING_PAYMENT, self.Status.CONFIRMED}:
            return False
        cutoff = self.show.start_time - timedelta(hours=2)
        return timezone.now() < cutoff

    def generate_qr_code_data_uri(self) -> str:
        seat_labels = ", ".join(
            bs.show_seat.seat.label for bs in self.booking_seats.select_related("show_seat__seat")
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

            seat_ids = list(
                locked_booking.booking_seats.values_list("show_seat_id", flat=True)
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

            was_paid = locked_booking.payment_status == self.PaymentStatus.PAID
            locked_booking.status = self.Status.CANCELLED
            locked_booking.payment_status = (
                self.PaymentStatus.REFUNDED if was_paid else self.PaymentStatus.FAILED
            )
            locked_booking.save(update_fields=["status", "payment_status", "updated_at"])
            return locked_booking

    def __str__(self):
        return f"{self.booking_reference} ({self.user.username})"


class BookingSeat(models.Model):
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="booking_seats"
    )
    show_seat = models.ForeignKey(
        ShowSeat, on_delete=models.PROTECT, related_name="booking_entries"
    )
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "show_seat"], name="unique_show_seat_per_booking"
            )
        ]

    def __str__(self):
        return f"{self.booking.booking_reference} -> {self.show_seat.seat.label}"

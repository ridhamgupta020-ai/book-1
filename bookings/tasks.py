from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Prefetch
from django.utils import timezone

from .models import Booking, BookingSeat, PaymentAttempt
from .payments import PaymentGatewayService
from .tickets import render_booking_ticket_pdf


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_booking_ticket_email(self, booking_id: int) -> bool:
    booking = (
        Booking.objects.select_related(
            "user", "show__movie", "show__screen", "show__screen__theatre"
        )
        .prefetch_related(
            Prefetch(
                "booking_seats",
                queryset=BookingSeat.objects.filter(is_active=True).select_related(
                    "show_seat__seat"
                ),
            )
        )
        .get(pk=booking_id)
    )
    if (
        booking.status != Booking.Status.CONFIRMED
        or booking.payment_status != Booking.PaymentStatus.PAID
    ):
        return False
    if not booking.user.email:
        raise ValueError(
            f"Cannot email ticket for booking {booking.booking_reference}: user has no email address."
        )

    email = EmailMessage(
        subject=f"Your MyBookShow ticket — {booking.show.movie.title}",
        body=(
            f"Hi {booking.user.get_full_name() or booking.user.username},\n\n"
            f"Your booking {booking.booking_reference} is confirmed. "
            "Your PDF ticket is attached. Scan its QR code at the theater.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[booking.user.email],
    )
    email.attach(
        f"ticket-{booking.booking_reference}.pdf",
        render_booking_ticket_pdf(booking),
        "application/pdf",
    )
    if email.send(fail_silently=False) != 1:
        raise RuntimeError(
            f"Ticket email for booking {booking.booking_reference} was not accepted by the email backend."
        )
    return True


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=8,
)
def expire_reservation(self, booking_id: int) -> str:
    return PaymentGatewayService.reconcile_expired_booking(booking_id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=8,
)
def cleanup_expired_reservations(self) -> int:
    now = timezone.now()
    expired_ids = Booking.objects.filter(
        status=Booking.Status.PENDING_PAYMENT,
        expires_at__lte=now,
    ).values_list("id", flat=True)
    queued = 0
    for booking_id in expired_ids.iterator(chunk_size=500):
        expire_reservation.delay(booking_id)
        queued += 1
    return queued


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=8,
)
def refund_late_payment(self, attempt_id: int) -> bool:
    return PaymentGatewayService.process_refund(attempt_id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=8,
)
def refund_booking(self, booking_id: int) -> int:
    attempts = Booking.objects.get(pk=booking_id).payment_attempts.filter(
        status__in=[
            PaymentAttempt.Status.SUCCESS,
            PaymentAttempt.Status.REFUND_PENDING,
            PaymentAttempt.Status.PARTIALLY_REFUNDED,
        ]
    )
    for attempt in attempts.iterator():
        PaymentGatewayService.process_refund(attempt.pk)
    return attempts.count()

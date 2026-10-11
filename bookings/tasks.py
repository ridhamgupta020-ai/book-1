from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Booking
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
        .prefetch_related("booking_seats__show_seat__seat")
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

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.core import signing
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from movies.models import Show
from .forms import SeatSelectionForm
from .models import Booking, BookingSeat
from .payments import PaymentGatewayService, PaymentGatewayUnavailable
from .tickets import render_booking_ticket_pdf


logger = logging.getLogger(__name__)
ACTIVE_BOOKING_SEATS = Prefetch(
    "booking_seats",
    queryset=BookingSeat.objects.filter(is_active=True).select_related(
        "show_seat__seat"
    ),
)


@login_required
def seat_selection_view(request, show_id):
    show = get_object_or_404(
        Show.objects.select_related("movie", "screen", "screen__theatre"),
        pk=show_id,
        is_active=True,
    )
    expired_booking_ids = Booking.objects.filter(
        show=show,
        status=Booking.Status.PENDING_PAYMENT,
        expires_at__lte=timezone.now(),
    ).values_list("id", flat=True)
    for booking_id in expired_booking_ids:
        PaymentGatewayService.reconcile_expired_booking(booking_id)
    show.initialize_show_seats()
    booking_reference = request.GET.get("booking", "").strip()
    booking = None
    if booking_reference:
        booking = get_object_or_404(
            Booking.objects.select_related("show"),
            booking_reference=booking_reference,
            user=request.user,
            show=show,
            status=Booking.Status.PENDING_PAYMENT,
        )
        if not booking.expires_at or booking.expires_at <= timezone.now():
            messages.error(request, "This seat reservation has expired.")
            return redirect("bookings:seat_selection", show_id=show.pk)
    show_seats = show.show_seats.select_related("seat").all()
    selected_seat_ids = set()
    if booking:
        selected_seat_ids = set(
            booking.booking_seats.filter(is_active=True).values_list(
                "show_seat_id", flat=True
            )
        )

    rows = {}
    for ss in show_seats:
        rows.setdefault(ss.seat.row_label, []).append(ss)

    if request.method == "POST":
        form = SeatSelectionForm(request.POST)
        if form.is_valid():
            try:
                if booking:
                    booking.update_pending_seats(form.cleaned_data["seat_ids"])
                else:
                    booking = Booking.create_pending_booking(
                        user=request.user,
                        show=show,
                        show_seat_ids=form.cleaned_data["seat_ids"],
                    )
                return redirect(
                    "bookings:checkout", booking_reference=booking.booking_reference
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Please select valid seats to continue.")

    return render(
        request,
        "bookings/seat_selection.html",
        {
            "show": show,
            "rows": rows,
            "booking": booking,
            "selected_seat_ids": selected_seat_ids,
        },
    )


@require_GET
def seat_availability_view(request, show_id):
    show = get_object_or_404(Show, pk=show_id, is_active=True)
    booking_reference = request.GET.get("booking", "").strip()
    booking = None
    if booking_reference and request.user.is_authenticated:
        booking = get_object_or_404(
            Booking,
            booking_reference=booking_reference,
            user=request.user,
            show=show,
            status=Booking.Status.PENDING_PAYMENT,
        )
    booking_seat_ids = set()
    if booking:
        booking_seat_ids = set(
            booking.booking_seats.filter(is_active=True).values_list(
                "show_seat_id", flat=True
            )
        )
    expired_booking_ids = Booking.objects.filter(
        show=show,
        status=Booking.Status.PENDING_PAYMENT,
        expires_at__lte=timezone.now(),
    ).values_list("id", flat=True)
    for booking_id in expired_booking_ids:
        PaymentGatewayService.reconcile_expired_booking(booking_id)
    show_seats = (
        show.show_seats.select_related("seat")
        .order_by("seat__row_label", "seat__seat_number")
    )
    return JsonResponse(
        {
            "seats": [
                {
                    "id": seat.pk,
                    "label": seat.seat.label,
                    "status": seat.status,
                    "price": str(seat.effective_price),
                    "held_by_current_booking": seat.pk in booking_seat_ids
                    and seat.held_by_id == request.user.id,
                }
                for seat in show_seats
            ],
            "server_time": timezone.now().isoformat(),
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def checkout_view(request, booking_reference):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        ).prefetch_related(ACTIVE_BOOKING_SEATS),
        booking_reference=booking_reference,
        user=request.user,
    )
    if booking.status == Booking.Status.CONFIRMED:
        return redirect(
            "bookings:ticket_detail", booking_reference=booking.booking_reference
        )

    if (
        booking.status != Booking.Status.PENDING_PAYMENT
        or not booking.expires_at
        or booking.expires_at <= timezone.now()
    ):
        messages.error(request, "This booking is no longer available for payment.")
        return redirect("bookings:my_bookings")

    if request.method == "POST":
        try:
            payment_order = PaymentGatewayService.create_payment_order(booking)
        except ValidationError as exc:
            return JsonResponse({"error": "; ".join(exc.messages)}, status=400)
        except ImproperlyConfigured as exc:
            logger.error("Razorpay checkout configuration error: %s", exc)
            return JsonResponse(
                {"error": "Online payments are temporarily unavailable."},
                status=503,
            )
        except PaymentGatewayUnavailable as exc:
            return JsonResponse({"error": str(exc)}, status=502)
        return JsonResponse(payment_order)

    return render(
        request,
        "bookings/checkout.html",
        {
            "booking": booking,
            "can_modify_seats": not booking.payment_attempts.exists(),
        },
    )


@login_required
@require_POST
def retry_payment_view(request, booking_reference):
    booking = get_object_or_404(
        Booking, booking_reference=booking_reference, user=request.user
    )
    if not booking.can_retry_payment:
        messages.error(request, "This payment is not currently eligible for retry.")
        return redirect("bookings:my_bookings")
    return redirect("bookings:checkout", booking_reference=booking.booking_reference)


@login_required
@require_POST
def verify_payment_callback_view(request, booking_reference):
    booking = get_object_or_404(
        Booking, booking_reference=booking_reference, user=request.user
    )
    order_id = request.POST.get("razorpay_order_id", "").strip()
    transaction_id = request.POST.get("razorpay_payment_id", "").strip()
    signature = request.POST.get("razorpay_signature", "").strip()

    try:
        PaymentGatewayService.verify_and_confirm_payment(
            booking=booking,
            order_id=order_id,
            transaction_id=transaction_id,
            signature=signature,
        )
        booking.refresh_from_db()
        if booking.status == Booking.Status.CONFIRMED:
            messages.success(
                request,
                f"Booking {booking.booking_reference} confirmed! Your e-ticket is ready.",
            )
        else:
            messages.warning(
                request,
                "Payment was received after the seat reservation expired. "
                "A refund is being processed automatically.",
            )
        return redirect(
            "bookings:ticket_detail", booking_reference=booking.booking_reference
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect(
            "bookings:checkout", booking_reference=booking.booking_reference
        )


@csrf_exempt
@require_POST
def razorpay_webhook_view(request):
    try:
        processed = PaymentGatewayService.handle_webhook(
            body=request.body,
            signature=request.headers.get("X-Razorpay-Signature", ""),
            event_id=request.headers.get("X-Razorpay-Event-Id", ""),
        )
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)
    except ImproperlyConfigured:
        logger.exception("Razorpay webhook secret is not configured.")
        return JsonResponse({"error": "Webhook processing unavailable."}, status=503)
    except Exception:
        logger.exception("Razorpay webhook processing failed.")
        return JsonResponse({"error": "Webhook processing failed."}, status=500)
    return JsonResponse({"received": True, "processed": processed})


@login_required
def ticket_detail_view(request, booking_reference):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        ).prefetch_related(ACTIVE_BOOKING_SEATS),
        booking_reference=booking_reference,
        user=request.user,
        status=Booking.Status.CONFIRMED,
        payment_status=Booking.PaymentStatus.PAID,
    )
    qr_data_uri = booking.generate_qr_code_data_uri()
    return render(
        request,
        "bookings/ticket_detail.html",
        {
            "booking": booking,
            "qr_data_uri": qr_data_uri,
        },
    )


@login_required
def ticket_download_view(request, booking_reference):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "show__movie", "show__screen", "show__screen__theatre"
        ).prefetch_related(ACTIVE_BOOKING_SEATS),
        booking_reference=booking_reference,
        user=request.user,
        status=Booking.Status.CONFIRMED,
        payment_status=Booking.PaymentStatus.PAID,
    )
    response = HttpResponse(
        render_booking_ticket_pdf(booking), content_type="application/pdf"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="ticket-{booking.booking_reference}.pdf"'
    )
    return response


def verify_ticket_view(request):
    token = request.GET.get("token", "")
    try:
        payload = signing.loads(token, salt="bookings.ticket-verification")
    except signing.BadSignature:
        return render(
            request,
            "bookings/ticket_verification.html",
            {"is_valid": False},
            status=400,
        )

    booking = (
        Booking.objects.select_related(
            "show__movie", "show__screen", "show__screen__theatre"
        )
        .prefetch_related(ACTIVE_BOOKING_SEATS)
        .filter(
            pk=payload.get("booking_id"),
            payment_transaction_id=payload.get("payment_reference"),
            status=Booking.Status.CONFIRMED,
            payment_status=Booking.PaymentStatus.PAID,
        )
        .first()
    )
    return render(
        request,
        "bookings/ticket_verification.html",
        {"is_valid": booking is not None, "booking": booking},
        status=200 if booking else 404,
    )


@login_required
def my_bookings_view(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        )
        .prefetch_related(
            "booking_seats__show_seat__seat",
            "payment_attempts",
            "payment_transactions",
        )
    )
    return render(request, "bookings/my_bookings.html", {"bookings": bookings})


@login_required
@require_POST
def cancel_booking_view(request, booking_reference):
    booking = get_object_or_404(
        Booking, booking_reference=booking_reference, user=request.user
    )
    try:
        booking.cancel_booking()
        messages.info(
            request,
            f"Booking {booking.booking_reference} has been cancelled and seats released.",
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("bookings:my_bookings")

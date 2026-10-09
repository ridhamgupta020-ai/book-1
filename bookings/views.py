import secrets
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from movies.models import Show
from .forms import SeatSelectionForm
from .models import Booking
from .payments import PaymentGatewayService


@login_required
def seat_selection_view(request, show_id):
    show = get_object_or_404(
        Show.objects.select_related("movie", "screen", "screen__theatre"),
        pk=show_id,
        is_active=True,
    )
    show.initialize_show_seats()
    show_seats = show.show_seats.select_related("seat").all()

    rows = {}
    for ss in show_seats:
        rows.setdefault(ss.seat.row_label, []).append(ss)

    if request.method == "POST":
        form = SeatSelectionForm(request.POST)
        if form.is_valid():
            try:
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
        },
    )


@login_required
def checkout_view(request, booking_reference):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        ).prefetch_related("booking_seats__show_seat__seat"),
        booking_reference=booking_reference,
        user=request.user,
    )
    if booking.status == Booking.Status.CONFIRMED:
        return redirect(
            "bookings:ticket_detail", booking_reference=booking.booking_reference
        )

    payment_order = PaymentGatewayService.create_payment_order(booking)
    demo_txn_id = f"TXN-{secrets.token_hex(5).upper()}"
    demo_signature = PaymentGatewayService.generate_gateway_signature(
        order_id=payment_order["order_id"],
        transaction_id=demo_txn_id,
        amount=payment_order["amount"],
    )

    return render(
        request,
        "bookings/checkout.html",
        {
            "booking": booking,
            "payment_order": payment_order,
            "demo_txn_id": demo_txn_id,
            "demo_signature": demo_signature,
        },
    )


@login_required
@require_POST
def verify_payment_callback_view(request, booking_reference):
    booking = get_object_or_404(
        Booking, booking_reference=booking_reference, user=request.user
    )
    order_id = request.POST.get("order_id", "").strip()
    transaction_id = request.POST.get("transaction_id", "").strip()
    signature = request.POST.get("signature", "").strip()

    try:
        PaymentGatewayService.verify_and_confirm_payment(
            booking=booking,
            order_id=order_id,
            transaction_id=transaction_id,
            signature=signature,
        )
        messages.success(
            request,
            f"Booking {booking.booking_reference} confirmed! Your e-ticket is ready.",
        )
        return redirect(
            "bookings:ticket_detail", booking_reference=booking.booking_reference
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect(
            "bookings:checkout", booking_reference=booking.booking_reference
        )


@login_required
def ticket_detail_view(request, booking_reference):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        ).prefetch_related("booking_seats__show_seat__seat"),
        booking_reference=booking_reference,
        user=request.user,
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
def my_bookings_view(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related(
            "show", "show__movie", "show__screen", "show__screen__theatre"
        )
        .prefetch_related("booking_seats__show_seat__seat")
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

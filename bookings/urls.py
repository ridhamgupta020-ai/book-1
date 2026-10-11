from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    path("my-bookings/", views.my_bookings_view, name="my_bookings"),
    path("show/<int:show_id>/seats/", views.seat_selection_view, name="seat_selection"),
    path("show/<int:show_id>/availability/", views.seat_availability_view, name="seat_availability"),
    path("<str:booking_reference>/checkout/", views.checkout_view, name="checkout"),
    path(
        "<str:booking_reference>/retry-payment/",
        views.retry_payment_view,
        name="retry_payment",
    ),
    path(
        "<str:booking_reference>/payment-callback/",
        views.verify_payment_callback_view,
        name="payment_callback",
    ),
    path("razorpay/webhook/", views.razorpay_webhook_view, name="razorpay_webhook"),
    path("ticket/verify/", views.verify_ticket_view, name="verify_ticket"),
    path(
        "<str:booking_reference>/ticket/download/",
        views.ticket_download_view,
        name="ticket_download",
    ),
    path("<str:booking_reference>/ticket/", views.ticket_detail_view, name="ticket_detail"),
    path("<str:booking_reference>/cancel/", views.cancel_booking_view, name="cancel_booking"),
]

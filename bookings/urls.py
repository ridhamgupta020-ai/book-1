from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    path("my-bookings/", views.my_bookings_view, name="my_bookings"),
    path("show/<int:show_id>/seats/", views.seat_selection_view, name="seat_selection"),
    path("<str:booking_reference>/checkout/", views.checkout_view, name="checkout"),
    path(
        "<str:booking_reference>/payment-callback/",
        views.verify_payment_callback_view,
        name="payment_callback",
    ),
    path("<str:booking_reference>/ticket/", views.ticket_detail_view, name="ticket_detail"),
    path("<str:booking_reference>/cancel/", views.cancel_booking_view, name="cancel_booking"),
]

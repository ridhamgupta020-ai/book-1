from django.contrib import admin
from .models import Booking, BookingSeat


class BookingSeatInline(admin.TabularInline):
    model = BookingSeat
    extra = 0
    readonly_fields = ("show_seat", "price")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_reference",
        "user",
        "show",
        "total_amount",
        "status",
        "payment_status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "created_at")
    search_fields = ("booking_reference", "user__username", "user__email", "payment_transaction_id")
    readonly_fields = ("booking_reference", "created_at", "updated_at")
    inlines = [BookingSeatInline]

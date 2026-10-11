from django.contrib import admin
from django.utils import timezone
from .models import Booking, BookingSeat, GatewayWebhookEvent, PaymentAttempt, PaymentTransaction


class BookingSeatInline(admin.TabularInline):
    model = BookingSeat
    extra = 0
    readonly_fields = ("show_seat", "price", "is_active")


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
    actions = ["check_in_bookings"]

    @admin.action(description="Check in selected confirmed ticket holders")
    def check_in_bookings(self, request, queryset):
        checked_in = 0
        for booking in queryset.filter(
            status=Booking.Status.CONFIRMED,
            payment_status=Booking.PaymentStatus.PAID,
            show__start_time__lte=timezone.now(),
        ):
            booking.checked_in_at = timezone.now()
            booking.save(update_fields=["checked_in_at", "updated_at"])
            self.log_change(request, booking, "Ticket holder checked in.")
            checked_in += 1
        self.message_user(request, f"Checked in {checked_in} ticket holder(s).")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("gateway_order_id", "booking", "amount", "status", "created_at")
    list_filter = ("gateway", "status", "created_at")
    search_fields = (
        "gateway_order_id",
        "gateway_payment_id",
        "booking__booking_reference",
    )
    readonly_fields = tuple(field.name for field in PaymentAttempt._meta.fields)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "gateway_payment_id",
        "booking",
        "amount",
        "status",
        "payment_method",
        "created_at",
    )
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("gateway_payment_id", "booking__booking_reference")
    readonly_fields = tuple(field.name for field in PaymentTransaction._meta.fields)


@admin.register(GatewayWebhookEvent)
class GatewayWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at", "created_at")
    list_filter = ("event_type", "processed_at")
    search_fields = ("event_id",)
    readonly_fields = tuple(field.name for field in GatewayWebhookEvent._meta.fields)

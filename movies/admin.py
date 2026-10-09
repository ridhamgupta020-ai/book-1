from django.contrib import admin
from .models import Movie, Screen, Seat, Show, ShowSeat, Theatre


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "genre",
        "language",
        "certificate",
        "duration_minutes",
        "release_date",
        "status",
        "is_featured",
    )
    list_filter = ("status", "genre", "language", "certificate", "is_featured")
    search_fields = ("title", "director", "cast")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-release_date",)


@admin.register(Theatre)
class TheatreAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "is_active", "created_at")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city", "address")


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("name", "theatre", "total_rows", "seats_per_row", "sound_system")
    list_filter = ("theatre__city", "sound_system")
    search_fields = ("name", "theatre__name")


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("screen", "row_label", "seat_number", "seat_type", "price_multiplier")
    list_filter = ("seat_type", "screen__theatre")
    search_fields = ("screen__name", "row_label")


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):
    list_display = ("movie", "screen", "start_time", "end_time", "ticket_price", "is_active")
    list_filter = ("is_active", "screen__theatre__city", "start_time")
    search_fields = ("movie__title", "screen__theatre__name")


@admin.register(ShowSeat)
class ShowSeatAdmin(admin.ModelAdmin):
    list_display = ("show", "seat", "status", "held_by", "held_until", "updated_at")
    list_filter = ("status",)
    search_fields = ("show__movie__title", "seat__row_label")

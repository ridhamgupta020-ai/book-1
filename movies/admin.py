from django.contrib import admin
from .models import (
    Movie,
    MoviePoster,
    Review,
    ReviewReport,
    Screen,
    Seat,
    Show,
    ShowSeat,
    Theatre,
)


class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "genre",
        "language",
        "certificate",
        "duration_minutes",
        "release_date",
        "rating",
        "status",
        "is_featured",
    )
    list_filter = ("status", "genre", "language", "certificate", "is_featured")
    search_fields = ("title", "director", "cast")
    readonly_fields = ("rating", "created_at")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-release_date",)
    inlines = [MoviePosterInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "movie",
        "user",
        "rating",
        "moderation_status",
        "created_at",
    )
    list_filter = ("moderation_status", "rating", "created_at")
    search_fields = ("movie__title", "user__username", "title", "text")
    readonly_fields = ("movie", "user", "booking", "created_at", "updated_at")
    list_editable = ("moderation_status",)


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ("review", "reporter", "reason", "status", "created_at")
    list_filter = ("status", "reason", "created_at")
    search_fields = ("review__movie__title", "reporter__username", "explanation")
    readonly_fields = ("review", "reporter", "reason", "explanation", "created_at")
    list_editable = ("status",)


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

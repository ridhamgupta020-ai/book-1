from decimal import Decimal
import re
import uuid
from urllib.parse import parse_qs, urlparse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.urls import reverse
from django.templatetags.static import static
from django.utils.text import slugify


DEFAULT_POSTER_PATH = "images/poster_chronos_horizon_1791521096648.jpg"
YOUTUBE_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def validate_poster_size(file_obj):
    max_bytes = 5 * 1024 * 1024
    if file_obj and file_obj.size > max_bytes:
        raise ValidationError("Poster file size must not exceed 5 MB.")


def validate_youtube_trailer_url(value):
    if not value:
        return
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/")):
            video_id = parsed.path.split("/")[2]
    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    if parsed.scheme != "https" or not YOUTUBE_VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValidationError("Enter a valid HTTPS YouTube trailer URL.")


def movie_poster_upload_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"movie-posters/{uuid.uuid4().hex}.{extension}"


class Movie(models.Model):
    class Status(models.TextChoices):
        NOW_SHOWING = "now_showing", "Now Showing"
        COMING_SOON = "coming_soon", "Coming Soon"
        ARCHIVED = "archived", "Archived"

    class Certificate(models.TextChoices):
        U = "U", "U (Universal)"
        UA = "UA", "U/A (Parental Guidance)"
        A = "A", "A (Adults Only)"
        S = "S", "S (Restricted)"

    title = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField()
    poster = models.ImageField(
        upload_to="posters/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
            validate_poster_size,
        ],
    )
    poster_url = models.URLField(blank=True, default="")
    genre = models.CharField(max_length=100, db_index=True)
    language = models.CharField(max_length=80, db_index=True)
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    release_date = models.DateField(db_index=True)
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=Decimal("0.0"),
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("5.0")),
        ],
        help_text="Average of published verified reviews, from 0 to 5.",
    )
    trailer_url = models.URLField(
        blank=True, default="", validators=[validate_youtube_trailer_url]
    )
    certificate = models.CharField(
        max_length=8, choices=Certificate.choices, default=Certificate.UA
    )
    cast = models.CharField(max_length=500)
    director = models.CharField(max_length=160)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOW_SHOWING, db_index=True
    )
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_featured", "-release_date", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug_candidate = base_slug
            counter = 1
            while Movie.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                counter += 1
                slug_candidate = f"{base_slug}-{counter}"
            self.slug = slug_candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("movies:movie_detail", kwargs={"slug": self.slug})

    @property
    def display_poster_url(self):
        if self.poster:
            return self.poster.url
        return self.poster_url or static(DEFAULT_POSTER_PATH)

    @property
    def trailer_embed_url(self):
        if not self.trailer_url:
            return ""
        parsed = urlparse(self.trailer_url)
        host = (parsed.hostname or "").lower()
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/")):
            video_id = parsed.path.split("/")[2]
        else:
            return ""
        if not YOUTUBE_VIDEO_ID_PATTERN.fullmatch(video_id):
            return ""
        return f"https://www.youtube-nocookie.com/embed/{video_id}"

    def __str__(self):
        return f"{self.title} ({self.language})"


class Theatre(models.Model):
    name = models.CharField(max_length=180)
    city = models.CharField(max_length=100, db_index=True)
    address = models.TextField()
    amenities = models.CharField(
        max_length=255, default="Dolby Atmos, 4K Laser Projection, Recliner Seating"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["city", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "city"], name="unique_theatre_name_per_city"
            )
        ]

    def __str__(self):
        return f"{self.name} — {self.city}"


class Screen(models.Model):
    theatre = models.ForeignKey(
        Theatre, on_delete=models.CASCADE, related_name="screens"
    )
    name = models.CharField(max_length=80)
    total_rows = models.PositiveSmallIntegerField(default=6)
    seats_per_row = models.PositiveSmallIntegerField(default=10)
    sound_system = models.CharField(max_length=80, default="Dolby Atmos")

    class Meta:
        ordering = ["theatre", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["theatre", "name"], name="unique_screen_per_theatre"
            )
        ]

    def __str__(self):
        return f"{self.theatre.name} | {self.name}"


class Seat(models.Model):
    class SeatCategory(models.TextChoices):
        STANDARD = "standard", "Standard"
        EXECUTIVE = "executive", "Executive"
        ROYAL = "royal", "Royal Recliner"

    screen = models.ForeignKey(
        Screen, on_delete=models.CASCADE, related_name="seats"
    )
    row_label = models.CharField(max_length=4)
    seat_number = models.PositiveSmallIntegerField()
    seat_type = models.CharField(
        max_length=20, choices=SeatCategory.choices, default=SeatCategory.STANDARD
    )
    price_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00")
    )

    class Meta:
        ordering = ["row_label", "seat_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "row_label", "seat_number"],
                name="unique_seat_per_screen",
            )
        ]

    @property
    def label(self) -> str:
        return f"{self.row_label}{self.seat_number}"

    def __str__(self):
        return f"{self.screen} - {self.label} ({self.get_seat_type_display()})"


class Show(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="shows")
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="shows")
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    ticket_price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("1.00"))]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Show end time must be after start time.")
        if self.screen_id and self.start_time and self.end_time:
            overlapping = Show.objects.filter(
                screen_id=self.screen_id,
                is_active=True,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    "This screen already has an overlapping active showtime."
                )

    def initialize_show_seats(self):
        """Ensure ShowSeat rows exist for every physical Seat on the screen."""
        screen_seats = list(self.screen.seats.all())
        existing_seat_ids = set(
            self.show_seats.values_list("seat_id", flat=True)
        )
        new_show_seats = [
            ShowSeat(show=self, seat=seat, status=ShowSeat.Status.AVAILABLE)
            for seat in screen_seats
            if seat.id not in existing_seat_ids
        ]
        if new_show_seats:
            ShowSeat.objects.bulk_create(new_show_seats, ignore_conflicts=True)

    def __str__(self):
        return f"{self.movie.title} @ {self.screen} ({self.start_time:%d %b %Y %H:%M})"


class ShowSeat(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        HELD = "held", "Temporarily Held"
        BOOKED = "booked", "Booked"

    show = models.ForeignKey(
        Show, on_delete=models.CASCADE, related_name="show_seats"
    )
    seat = models.ForeignKey(
        Seat, on_delete=models.CASCADE, related_name="show_instances"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    held_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="held_show_seats",
    )
    held_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["seat__row_label", "seat__seat_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["show", "seat"], name="unique_seat_per_show"
            )
        ]

    @property
    def effective_price(self) -> Decimal:
        return (self.show.ticket_price * self.seat.price_multiplier).quantize(
            Decimal("0.01")
        )

    def __str__(self):
        return f"{self.show_id}:{self.seat.label} [{self.status}]"


class MoviePoster(models.Model):
    movie = models.ForeignKey(
        Movie, on_delete=models.CASCADE, related_name="posters"
    )
    image = models.ImageField(
        upload_to=movie_poster_upload_path,
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
            validate_poster_size,
        ],
    )
    alt_text = models.CharField(max_length=200, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["movie"],
                condition=models.Q(is_primary=True),
                name="one_primary_poster_per_movie",
            )
        ]

    def clean(self):
        super().clean()
        if self.image:
            try:
                from PIL import Image

                image = Image.open(self.image)
                image.verify()
            except (OSError, ValueError) as exc:
                raise ValidationError({"image": "Upload a valid image file."}) from exc


class Review(models.Model):
    class ModerationStatus(models.TextChoices):
        PENDING = "pending", "Pending moderation"
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden"
        REJECTED = "rejected", "Rejected"

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="movie_reviews",
    )
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="movie_reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=120)
    text = models.TextField(max_length=3000)
    moderation_status = models.CharField(
        max_length=16,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "movie"], name="one_review_per_booking_movie"
            )
        ]
        indexes = [models.Index(fields=["movie", "moderation_status"])]

    @property
    def is_verified_viewer(self):
        return bool(self.booking.checked_in_at)

    def clean(self):
        super().clean()
        if not self.booking_id or not self.movie_id or not self.user_id:
            return
        if (
            self.booking.user_id != self.user_id
            or self.booking.show.movie_id != self.movie_id
            or self.booking.status != "confirmed"
            or self.booking.payment_status != "paid"
            or not self.booking.checked_in_at
            or self.booking.show.end_time > timezone.now()
        ):
            raise ValidationError(
                "A verified check-in for a completed paid show is required to review this movie."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        previous_movie_id = None
        if self.pk:
            previous_movie_id = Review.objects.filter(pk=self.pk).values_list(
                "movie_id", flat=True
            ).first()
        super().save(*args, **kwargs)
        recalculate_movie_rating(self.movie_id)
        if previous_movie_id and previous_movie_id != self.movie_id:
            recalculate_movie_rating(previous_movie_id)

    def delete(self, *args, **kwargs):
        movie_id = self.movie_id
        result = super().delete(*args, **kwargs)
        recalculate_movie_rating(movie_id)
        return result


def recalculate_movie_rating(movie_id):
    from django.db.models import Avg, Count

    stats = Review.objects.filter(
        movie_id=movie_id, moderation_status=Review.ModerationStatus.PUBLISHED
    ).aggregate(rating=Avg("rating"), total=Count("id"))
    Movie.objects.filter(pk=movie_id).update(rating=stats["rating"] or Decimal("0.0"))


class ReviewReport(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACTIONED = "actioned", "Actioned"
        DISMISSED = "dismissed", "Dismissed"

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="reports"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_reports",
    )
    reason = models.CharField(max_length=80)
    explanation = models.CharField(max_length=1000, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["review", "reporter"], name="one_report_per_user_review"
            )
        ]

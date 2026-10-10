from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.templatetags.static import static
from django.utils.text import slugify


DEFAULT_POSTER_PATH = "images/poster_chronos_horizon_1791521096648.jpg"


def validate_poster_size(file_obj):
    max_bytes = 5 * 1024 * 1024
    if file_obj and file_obj.size > max_bytes:
        raise ValidationError("Poster file size must not exceed 5 MB.")


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

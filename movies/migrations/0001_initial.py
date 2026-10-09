from decimal import Decimal
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import movies.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Movie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(db_index=True, max_length=200)),
                ("slug", models.SlugField(max_length=220, unique=True)),
                ("description", models.TextField()),
                ("poster", models.ImageField(blank=True, null=True, upload_to="posters/", validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]), movies.models.validate_poster_size])),
                ("poster_url", models.URLField(blank=True, default="")),
                ("genre", models.CharField(db_index=True, max_length=100)),
                ("language", models.CharField(db_index=True, max_length=80)),
                ("duration_minutes", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("release_date", models.DateField(db_index=True)),
                ("certificate", models.CharField(choices=[("U", "U (Universal)"), ("UA", "U/A (Parental Guidance)"), ("A", "A (Adults Only)"), ("S", "S (Restricted)")], default="UA", max_length=8)),
                ("cast", models.CharField(max_length=500)),
                ("director", models.CharField(max_length=160)),
                ("status", models.CharField(choices=[("now_showing", "Now Showing"), ("coming_soon", "Coming Soon"), ("archived", "Archived")], db_index=True, default="now_showing", max_length=20)),
                ("is_featured", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-is_featured", "-release_date", "title"]},
        ),
        migrations.CreateModel(
            name="Theatre",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("city", models.CharField(db_index=True, max_length=100)),
                ("address", models.TextField()),
                ("amenities", models.CharField(default="Dolby Atmos, 4K Laser Projection, Recliner Seating", max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["city", "name"]},
        ),
        migrations.CreateModel(
            name="Screen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("total_rows", models.PositiveSmallIntegerField(default=6)),
                ("seats_per_row", models.PositiveSmallIntegerField(default=10)),
                ("sound_system", models.CharField(default="Dolby Atmos", max_length=80)),
                ("theatre", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="screens", to="movies.theatre")),
            ],
            options={"ordering": ["theatre", "name"]},
        ),
        migrations.CreateModel(
            name="Seat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_label", models.CharField(max_length=4)),
                ("seat_number", models.PositiveSmallIntegerField()),
                ("seat_type", models.CharField(choices=[("standard", "Standard"), ("executive", "Executive"), ("royal", "Royal Recliner")], default="standard", max_length=20)),
                ("price_multiplier", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=4)),
                ("screen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seats", to="movies.screen")),
            ],
            options={"ordering": ["row_label", "seat_number"]},
        ),
        migrations.CreateModel(
            name="Show",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_time", models.DateTimeField(db_index=True)),
                ("end_time", models.DateTimeField()),
                ("ticket_price", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("1.00"))])),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("movie", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shows", to="movies.movie")),
                ("screen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shows", to="movies.screen")),
            ],
            options={"ordering": ["start_time"]},
        ),
        migrations.CreateModel(
            name="ShowSeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("available", "Available"), ("held", "Temporarily Held"), ("booked", "Booked")], db_index=True, default="available", max_length=16)),
                ("held_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("held_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="held_show_seats", to=settings.AUTH_USER_MODEL)),
                ("seat", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="show_instances", to="movies.seat")),
                ("show", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="show_seats", to="movies.show")),
            ],
            options={"ordering": ["seat__row_label", "seat__seat_number"]},
        ),
        migrations.AddConstraint(
            model_name="theatre",
            constraint=models.UniqueConstraint(fields=("name", "city"), name="unique_theatre_name_per_city"),
        ),
        migrations.AddConstraint(
            model_name="screen",
            constraint=models.UniqueConstraint(fields=("theatre", "name"), name="unique_screen_per_theatre"),
        ),
        migrations.AddConstraint(
            model_name="seat",
            constraint=models.UniqueConstraint(fields=("screen", "row_label", "seat_number"), name="unique_seat_per_screen"),
        ),
        migrations.AddConstraint(
            model_name="showseat",
            constraint=models.UniqueConstraint(fields=("show", "seat"), name="unique_seat_per_show"),
        ),
    ]

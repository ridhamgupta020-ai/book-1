import bookings.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("movies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Booking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("booking_reference", models.CharField(db_index=True, default=bookings.models.generate_booking_reference, max_length=24, unique=True)),
                ("subtotal_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("convenience_fee", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(choices=[("pending_payment", "Pending Payment"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled"), ("expired", "Expired")], db_index=True, default="pending_payment", max_length=20)),
                ("payment_status", models.CharField(choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"), ("refunded", "Refunded")], default="pending", max_length=20)),
                ("payment_Order_id", models.CharField(blank=True, default="", max_length=120)),
                ("payment_transaction_id", models.CharField(blank=True, default="", max_length=120)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("show", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="movies.show")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bookings", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BookingSeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=2, max_digits=8)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="booking_seats", to="bookings.booking")),
                ("show_seat", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="booking_entries", to="movies.showseat")),
            ],
        ),
        migrations.AddConstraint(
            model_name="bookingseat",
            constraint=models.UniqueConstraint(fields=("booking", "show_seat"), name="unique_show_seat_per_booking"),
        ),
    ]

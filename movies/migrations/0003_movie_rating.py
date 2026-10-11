from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("movies", "0002_add_seeded_movie_posters"),
    ]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="rating",
            field=models.DecimalField(
                decimal_places=1,
                default=Decimal("0.0"),
                help_text="Editorial rating from 0 to 10.",
                max_digits=2,
                validators=[
                    MinValueValidator(Decimal("0.0")),
                    MaxValueValidator(Decimal("5.0")),
                ],
            ),
        ),
    ]

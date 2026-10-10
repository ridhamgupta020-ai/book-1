from django.db import migrations


POSTERS = {
    "chronos-horizon": "/static/images/poster_chronos_horizon_1791521096648.jpg",
    "velvet-nocturne": "/static/images/poster_velvet_nocturne_1791521110973.jpg",
    "the-monsoon-express": "/static/images/poster_monsoon_express_1791521122726.jpg",
    "silent-symphony": "/static/images/poster_silent_symphony_1791521135438.jpg",
}


def add_default_posters(apps, schema_editor):
    Movie = apps.get_model("movies", "Movie")
    for slug, poster_url in POSTERS.items():
        Movie.objects.filter(slug=slug, poster_url="").update(poster_url=poster_url)


def remove_default_posters(apps, schema_editor):
    Movie = apps.get_model("movies", "Movie")
    for slug, poster_url in POSTERS.items():
        Movie.objects.filter(slug=slug, poster_url=poster_url).update(poster_url="")


class Migration(migrations.Migration):
    dependencies = [
        ("movies", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_default_posters, remove_default_posters),
    ]

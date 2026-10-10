"""
Automatic startup database verification, migration, and catalog seeding for MyBookShow.
Ensures that deployments on Render and Vercel never return HTTP 500 due to:
1. Unmigrated database tables when custom Build Commands omit `manage.py migrate`.
2. IPv6-only direct Supabase hosts (`db.<ref>.supabase.co`) failing on IPv4-only PaaS containers,
   or placeholder `YOUR_PASSWORD` values in `DATABASE_URL`.
3. Empty initial movie/theatre/showtime tables.
"""

from datetime import date, timedelta
from decimal import Decimal
import logging
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.utils import DatabaseError
from django.utils import timezone


logger = logging.getLogger(__name__)


def ensure_database_ready():
    """
    Verifies database connectivity, falls back safely if `DATABASE_URL` is unreachable
    or contains unreplaced placeholders, runs pending migrations, and seeds initial data.
    """
    db_conn = connections["default"]
    try:
        db_conn.ensure_connection()
    except DatabaseError as exc:
        logger.warning(
            "Primary database connection failed (%s); switching to the local SQLite fallback. "
            "For Supabase, verify DATABASE_URL uses a reachable IPv4 Session Pooler.",
            type(exc).__name__,
        )
        db_conn.close()
        fallback_config = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(Path("/tmp/mybookshow_fallback.sqlite3")),
            "ATOMIC_REQUESTS": False,
            "AUTOCOMMIT": True,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "OPTIONS": {},
            "TIME_ZONE": None,
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
        }
        settings.DATABASES["default"] = fallback_config
        connections.settings["default"] = fallback_config
        db_conn.settings_dict = fallback_config
        db_conn = connections["default"]

    existing_tables = db_conn.introspection.table_names()
    if "movies_movie" not in existing_tables or "auth_user" not in existing_tables:
        logger.info("Running pending Django migrations.")
        call_command("migrate", interactive=False, verbosity=1)

    _seed_initial_catalog()


def _seed_initial_catalog():
    from movies.models import Movie, Screen, Seat, Show, Theatre

    if Movie.objects.exists():
        return

    logger.info("Seeding initial movies, theatres, screens, and showtimes.")
    today = date.today()
    movies_data = [
        {
            "title": "Chronos Horizon",
            "slug": "chronos-horizon",
            "description": (
                "When an orbital relay station near Cygnus X-1 begins receiving telemetry "
                "from forty years in the future, Commander Aarav Mehta leads a three-person "
                "deep-space crew across the event horizon."
            ),
            "genre": "Sci-Fi",
            "language": "English",
            "duration_minutes": 154,
            "release_date": today - timedelta(days=10),
            "poster_url": "/static/images/poster_chronos_horizon_1791521096648.jpg",
            "certificate": "UA",
            "cast": "Aarav Mehta, Elena Vance, Devika Rao, Marcus Sterling",
            "director": "Vikramaditya Sen",
            "status": "now_showing",
            "is_featured": True,
        },
        {
            "title": "Velvet Nocturne",
            "slug": "velvet-nocturne",
            "description": (
                "Set across rain-drenched South Mumbai jazz clubs over a single sleepless night, "
                "an acoustic forensic investigator unravels a decades-old conspiracy hidden inside "
                "an unreleased vinyl master."
            ),
            "genre": "Mystery",
            "language": "Hindi",
            "duration_minutes": 136,
            "release_date": today - timedelta(days=5),
            "poster_url": "/static/images/poster_velvet_nocturne_1791521110973.jpg",
            "certificate": "UA",
            "cast": "Kabir Bedi, Tara Sharma, Rajeev Khandelwal, Zoya Hussain",
            "director": "Rohan Sippy",
            "status": "now_showing",
            "is_featured": True,
        },
        {
            "title": "The Monsoon Express",
            "slug": "monsoon-express",
            "description": (
                "Aboard a heritage mountain locomotive stranded on a high stone viaduct in the "
                "Western Ghats during a torrential tempest, nine strangers must collaborate to "
                "secure the bridge before daybreak."
            ),
            "genre": "Thriller",
            "language": "Hindi",
            "duration_minutes": 128,
            "release_date": today - timedelta(days=2),
            "poster_url": "/static/images/poster_monsoon_express_1791521122726.jpg",
            "certificate": "UA",
            "cast": "Neeraj Kabi, Radhika Apte, Gulshan Devaiah, Tillotama Shome",
            "director": "Meghna Gulzar",
            "status": "now_showing",
            "is_featured": True,
        },
        {
            "title": "Silent Symphony",
            "slug": "silent-symphony",
            "description": (
                "Faced with progressive acoustic vertigo weeks before her Vienna Philharmonic "
                "debut, principal cellist Mira Deshmukh discovers a radical resonance technique "
                "that transforms how she perceives sound."
            ),
            "genre": "Drama",
            "language": "English",
            "duration_minutes": 122,
            "release_date": today + timedelta(days=14),
            "poster_url": "/static/images/poster_silent_symphony_1791521135438.jpg",
            "certificate": "U",
            "cast": "Mira Deshmukh, Julian Hirth, Adil Hussain",
            "director": "Chaitanya Tamhane",
            "status": "coming_soon",
            "is_featured": False,
        },
    ]

    created_movies = [Movie.objects.create(**m) for m in movies_data]

    theatres_data = [
        (
            "MyBookShow Grand IMAX — Palladium",
            "Mumbai",
            "Senapati Bapat Marg, Lower Parel, Mumbai 400013",
            "IMAX Dual 4K Laser, 12-Channel Sound, Luxury Recliners",
        ),
        (
            "MyBookShow Regal Atmos — Connaught Place",
            "Delhi",
            "Outer Circle, Connaught Place, New Delhi 110001",
            "Dolby Atmos, Barco RGB Laser, Valet Parking",
        ),
        (
            "MyBookShow Luxe — Indiranagar",
            "Bengaluru",
            "100 Feet Road, HAL 2nd Stage, Indiranagar, Bengaluru 560038",
            "4K Christie Laser, Gourmet Dining, Acoustic Pod Seating",
        ),
    ]

    now = timezone.now()
    for idx, (t_name, t_city, t_addr, t_amenities) in enumerate(theatres_data):
        theatre = Theatre.objects.create(
            name=t_name, city=t_city, address=t_addr, amenities=t_amenities
        )
        screen = Screen.objects.create(
            theatre=theatre,
            name="Audi 1 IMAX Laser" if idx == 0 else "Screen 1 Dolby Atmos",
            total_rows=6,
            seats_per_row=8,
            sound_system="IMAX 12-Channel" if idx == 0 else "Dolby Atmos",
        )
        for r_idx, row_label in enumerate(["A", "B", "C", "D", "E", "F"]):
            seat_type = (
                Seat.SeatCategory.ROYAL
                if r_idx == 5
                else (
                    Seat.SeatCategory.EXECUTIVE
                    if r_idx >= 2
                    else Seat.SeatCategory.STANDARD
                )
            )
            multiplier = (
                Decimal("1.50")
                if r_idx == 5
                else (Decimal("1.25") if r_idx >= 2 else Decimal("1.00"))
            )
            for seat_num in range(1, 9):
                Seat.objects.create(
                    screen=screen,
                    row_label=row_label,
                    seat_number=seat_num,
                    seat_type=seat_type,
                    price_multiplier=multiplier,
                )

        # Create upcoming shows for the active movies
        for m_idx, movie in enumerate(created_movies[:3]):
            start_time = now + timedelta(hours=4 + (m_idx * 3) + idx)
            end_time = start_time + timedelta(minutes=movie.duration_minutes + 15)
            show = Show.objects.create(
                movie=movie,
                screen=screen,
                start_time=start_time,
                end_time=end_time,
                ticket_price=Decimal("320.00") if idx == 0 else Decimal("280.00"),
            )
            show.initialize_show_seats()

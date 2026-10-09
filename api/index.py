import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path so bookmyseat is importable in Vercel serverless runtime
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Ensure database tables and initial sample catalog exist on cold start if using unmigrated DB
try:
    from django.core.management import call_command
    from django.db import connection

    existing_tables = connection.introspection.table_names()
    if "movies_movie" not in existing_tables:
        call_command("migrate", interactive=False, verbosity=0)

    from movies.models import Movie, Screen, Seat, Show, Theatre
    from django.utils import timezone

    if not Movie.objects.exists():
        m1 = Movie.objects.create(
            title="Chronos Horizon",
            slug="chronos-horizon",
            description="When an orbital relay station near Cygnus X-1 begins receiving telemetry from forty years in the future, Commander Aarav Mehta leads a deep-space crew across the event horizon.",
            genre="Sci-Fi",
            language="English",
            duration_minutes=154,
            release_date=date.today(),
            certificate="UA",
            cast="Aarav Mehta, Elena Vance, Devika Rao",
            director="Vikramaditya Sen",
            status="now_showing",
            is_featured=True,
        )
        m2 = Movie.objects.create(
            title="Velvet Nocturne",
            slug="velvet-nocturne",
            description="Set across rain-drenched South Mumbai jazz clubs over a single sleepless night, an acoustic forensic investigator unravels a conspiracy hidden inside an unreleased vinyl master.",
            genre="Mystery",
            language="Hindi",
            duration_minutes=136,
            release_date=date.today(),
            certificate="UA",
            cast="Kabir Bedi, Tara Sharma, Rajeev Khandelwal",
            director="Rohan Sippy",
            status="now_showing",
            is_featured=True,
        )
        theatre = Theatre.objects.create(
            name="MyBookShow Grand IMAX — Palladium",
            city="Mumbai",
            address="Senapati Bapat Marg, Lower Parel, Mumbai",
        )
        screen = Screen.objects.create(
            theatre=theatre,
            name="Audi 1 IMAX Laser",
            total_rows=4,
            seats_per_row=6,
        )
        for r_idx, row_label in enumerate(["A", "B", "C", "D"]):
            for s_num in range(1, 7):
                Seat.objects.create(
                    screen=screen,
                    row_label=row_label,
                    seat_number=s_num,
                    seat_type="royal" if r_idx == 3 else ("executive" if r_idx >= 1 else "standard"),
                    price_multiplier=Decimal("1.50") if r_idx == 3 else (Decimal("1.20") if r_idx >= 1 else Decimal("1.00")),
                )
        start_dt = timezone.now() + timedelta(hours=5)
        show1 = Show.objects.create(
            movie=m1,
            screen=screen,
            start_time=start_dt,
            end_time=start_dt + timedelta(minutes=154),
            ticket_price=Decimal("320.00"),
        )
        show1.initialize_show_seats()
        show2 = Show.objects.create(
            movie=m2,
            screen=screen,
            start_time=start_dt + timedelta(hours=3),
            end_time=start_dt + timedelta(hours=5, minutes=16),
            ticket_price=Decimal("280.00"),
        )
        show2.initialize_show_seats()
except Exception as exc:
    # Log non-fatal bootstrap warnings without crashing the WSGI handler
    print(f"[MyBookShow bootstrap notice]: {exc}")

app = application

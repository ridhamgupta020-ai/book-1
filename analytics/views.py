import csv
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import ExtractHour, TruncDate, TruncMonth, TruncWeek, TruncYear
from django.db.models.functions import Coalesce
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.utils import timezone

from bookings.models import Booking, BookingSeat, PaymentAttempt
from movies.models import Show, ShowSeat

MAX_RANGE_DAYS = 366
SHOW_OCCUPANCY_LIMIT = 100
RANKING_LIMIT = 10
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
PAID_CONFIRMED = Q(
    status=Booking.Status.CONFIRMED,
    payment_status=Booking.PaymentStatus.PAID,
)
FINANCIAL_STATUSES = [
    Booking.PaymentStatus.PAID,
    Booking.PaymentStatus.REFUND_PENDING,
    Booking.PaymentStatus.PARTIALLY_REFUNDED,
    Booking.PaymentStatus.REFUNDED,
]


def _staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_active or not (user.is_staff or user.is_superuser):
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)

    return wrapped


def _parse_date(value, field_name):
    if not value:
        return None, None
    if not DATE_PATTERN.fullmatch(value):
        return None, f"{field_name} must use YYYY-MM-DD format."
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, f"{field_name} must be a valid calendar date."


def _date_range(request):
    today = timezone.localdate()
    start, start_error = _parse_date(request.GET.get("start_date", ""), "Start date")
    end, end_error = _parse_date(request.GET.get("end_date", ""), "End date")
    errors = [message for message in (start_error, end_error) if message]

    if start is None and end is None:
        start, end = today - timedelta(days=29), today
    elif start is None:
        start = end - timedelta(days=29)
    elif end is None:
        end = today

    if not errors:
        if start > end:
            errors.append("Start date must be on or before end date.")
        elif (end - start).days + 1 > MAX_RANGE_DAYS:
            errors.append(f"Date range cannot exceed {MAX_RANGE_DAYS} days.")
    return start, end, errors


def _datetime_bounds(start, end):
    tz = timezone.get_current_timezone()
    lower = timezone.make_aware(datetime.combine(start, time.min), tz)
    upper = timezone.make_aware(
        datetime.combine(end + timedelta(days=1), time.min), tz
    )
    return lower, upper


def _chart_series(rows, value_key, *, date_bucket=True):
    maximum = max((row[value_key] or 0 for row in rows), default=0) or 1
    for row in rows:
        value = row[value_key] or 0
        row["bar_width"] = round(float(value / maximum * 100), 1)
        bucket = row["bucket"]
        row["label"] = (
            timezone.localtime(bucket).strftime("%d %b")
            if date_bucket and hasattr(bucket, "tzinfo")
            else bucket.strftime("%d %b")
            if date_bucket and hasattr(bucket, "strftime")
            else str(bucket)
        )
    return rows


def _report_context(start, end):
    lower, upper = _datetime_bounds(start, end)
    bookings = Booking.objects.filter(created_at__gte=lower, created_at__lt=upper)

    refunded_by_booking = (
        PaymentAttempt.objects.filter(booking_id=OuterRef("pk"))
        .values("booking_id")
        .annotate(value=Sum("refunded_amount"))
        .values("value")[:1]
    )
    financial_bookings = (
        bookings.filter(payment_status__in=FINANCIAL_STATUSES)
        .annotate(
            refunded=Coalesce(
                Subquery(refunded_by_booking),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .annotate(
            net_revenue=ExpressionWrapper(
                F("total_amount") - F("refunded"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
    )
    totals = financial_bookings.aggregate(
        gross_collected=Sum("total_amount"),
        refunded_amount=Sum("refunded"),
        net_revenue=Sum("net_revenue"),
        confirmed_bookings=Count("pk", filter=Q(status=Booking.Status.CONFIRMED)),
        paid_confirmed_bookings=Count("pk", filter=PAID_CONFIRMED),
    )
    totals["gross_collected"] = totals["gross_collected"] or Decimal("0.00")
    totals["refunded_amount"] = totals["refunded_amount"] or Decimal("0.00")
    totals["net_revenue"] = totals["net_revenue"] or Decimal("0.00")
    totals["confirmed_tickets"] = BookingSeat.objects.filter(
        booking__created_at__gte=lower,
        booking__created_at__lt=upper,
        booking__status=Booking.Status.CONFIRMED,
        is_active=True,
    ).count()

    booking_states = {value: 0 for value, _label in Booking.Status.choices}
    booking_states.update(
        {
            row["status"]: row["count"]
            for row in bookings.values("status").annotate(count=Count("pk"))
        }
    )

    paid_bookings = bookings.filter(PAID_CONFIRMED)
    revenue_by_day = _chart_series(
        list(
            financial_bookings.annotate(bucket=TruncDate("created_at"))
            .values("bucket")
            .annotate(value=Sum("net_revenue"))
            .order_by("bucket")
        ),
        "value",
    )
    revenue_by_week = _chart_series(
        list(
            financial_bookings.annotate(bucket=TruncWeek("created_at"))
            .values("bucket")
            .annotate(value=Sum("net_revenue"))
            .order_by("bucket")
        ),
        "value",
    )
    revenue_by_month = _chart_series(
        list(
            financial_bookings.annotate(bucket=TruncMonth("created_at"))
            .values("bucket")
            .annotate(value=Sum("net_revenue"))
            .order_by("bucket")
        ),
        "value",
    )
    revenue_by_year = _chart_series(
        list(
            financial_bookings.annotate(bucket=TruncYear("created_at"))
            .values("bucket")
            .annotate(value=Sum("net_revenue"))
            .order_by("bucket")
        ),
        "value",
    )
    booking_trends = _chart_series(
        list(
            bookings.annotate(bucket=TruncDate("created_at"))
            .values("bucket")
            .annotate(value=Count("pk"))
            .order_by("bucket")
        ),
        "value",
    )
    peak_booking_hours = list(
        bookings.annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(bookings=Count("pk"))
        .order_by("hour")
    )
    peak_hour_max = max(
        (row["bookings"] for row in peak_booking_hours), default=0
    ) or 1
    for hour in peak_booking_hours:
        hour["label"] = f"{hour['hour']:02d}:00"
        hour["bar_width"] = round(hour["bookings"] * 100 / peak_hour_max, 1)

    cancellations = Booking.objects.filter(
        cancelled_at__gte=lower,
        cancelled_at__lt=upper,
    ).aggregate(count=Count("pk"), value=Sum("total_amount"))
    refunds = PaymentAttempt.objects.filter(
        refunded_at__gte=lower,
        refunded_at__lt=upper,
        status__in=[
            PaymentAttempt.Status.REFUNDED,
            PaymentAttempt.Status.PARTIALLY_REFUNDED,
        ],
    ).aggregate(count=Count("pk"), value=Sum("refunded_amount"))
    pending_refunds = PaymentAttempt.objects.filter(
        status=PaymentAttempt.Status.REFUND_PENDING
    ).count()
    user_model = get_user_model()
    user_stats = {
        "total": user_model.objects.count(),
        "new": user_model.objects.filter(
            date_joined__gte=lower, date_joined__lt=upper
        ).count(),
        "repeat_customers": (
            paid_bookings.values("user_id")
            .annotate(booking_count=Count("pk"))
            .filter(booking_count__gt=1)
            .count()
        ),
    }

    movie_rankings = list(
        paid_bookings.values("show__movie_id", "show__movie__title")
        .annotate(gross=Sum("total_amount"), bookings=Count("pk"))
        .order_by("-gross", "show__movie__title")[:RANKING_LIMIT]
    )
    theatre_rankings = list(
        paid_bookings.values(
            "show__screen__theatre__name", "show__screen__theatre__city"
        )
        .annotate(gross=Sum("total_amount"), bookings=Count("pk"))
        .order_by("-gross", "show__screen__theatre__name")[:RANKING_LIMIT]
    )

    shows = Show.objects.filter(start_time__gte=lower, start_time__lt=upper)
    theatre_occupancy = list(
        shows.values(
            "screen__theatre__name",
            "screen__theatre__city",
        )
        .annotate(
            shows=Count("pk", distinct=True),
            sellable_seats=Count("show_seats"),
            booked_seats=Count(
                "show_seats", filter=Q(show_seats__status=ShowSeat.Status.BOOKED)
            ),
            held_seats=Count(
                "show_seats", filter=Q(show_seats__status=ShowSeat.Status.HELD)
            ),
        )
        .order_by("-booked_seats", "screen__theatre__name")
    )
    for theatre in theatre_occupancy:
        denominator = theatre["sellable_seats"]
        theatre["occupancy_percent"] = (
            theatre["booked_seats"] * 100 / denominator if denominator else 0
        )

    show_occupancy = list(
        shows.values(
            "pk",
            "movie__title",
            "screen__theatre__name",
            "screen__name",
            "start_time",
        )
        .annotate(
            sellable_seats=Count("show_seats"),
            booked_seats=Count(
                "show_seats", filter=Q(show_seats__status=ShowSeat.Status.BOOKED)
            ),
            held_seats=Count(
                "show_seats", filter=Q(show_seats__status=ShowSeat.Status.HELD)
            ),
        )
        .order_by("-start_time", "movie__title")[:SHOW_OCCUPANCY_LIMIT]
    )
    for show in show_occupancy:
        denominator = show["sellable_seats"]
        show["occupancy_percent"] = (
            show["booked_seats"] * 100 / denominator if denominator else 0
        )

    return {
        "start_date": start,
        "end_date": end,
        "totals": totals,
        "revenue_by_day": revenue_by_day,
        "revenue_by_week": revenue_by_week,
        "revenue_by_month": revenue_by_month,
        "revenue_by_year": revenue_by_year,
        "revenue_charts": [
            ("Daily net revenue", revenue_by_day),
            ("Weekly net revenue", revenue_by_week),
            ("Monthly net revenue", revenue_by_month),
            ("Yearly net revenue", revenue_by_year),
        ],
        "booking_trends": booking_trends,
        "peak_booking_hours": peak_booking_hours,
        "cancellations": cancellations,
        "refunds": refunds,
        "pending_refunds": pending_refunds,
        "user_stats": user_stats,
        "booking_states": booking_states,
        "movie_rankings": movie_rankings,
        "theatre_rankings": theatre_rankings,
        "theatre_occupancy": theatre_occupancy,
        "show_occupancy": show_occupancy,
        "max_range_days": MAX_RANGE_DAYS,
        "show_occupancy_limit": SHOW_OCCUPANCY_LIMIT,
    }


@_staff_required
def dashboard(request):
    start, end, errors = _date_range(request)
    if errors:
        return render(
            request,
            "analytics/dashboard.html",
            {
                "start_date": request.GET.get("start_date", ""),
                "end_date": request.GET.get("end_date", ""),
                "errors": errors,
                "max_range_days": MAX_RANGE_DAYS,
            },
            status=400,
        )
    return render(request, "analytics/dashboard.html", _report_context(start, end))


class _CsvBuffer:
    def write(self, value):
        return value


def _csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _csv_rows(start, end):
    lower, upper = _datetime_bounds(start, end)
    rows = (
        Booking.objects.filter(created_at__gte=lower, created_at__lt=upper)
        .values(
            "created_at",
            "booking_reference",
            "show__movie__title",
            "show__screen__theatre__name",
            "show__screen__theatre__city",
            "show__start_time",
            "status",
            "payment_status",
            "total_amount",
        )
        .annotate(
            ticket_count=Count(
                "booking_seats", filter=Q(booking_seats__is_active=True)
            )
        )
        .order_by("created_at", "pk")
        .iterator(chunk_size=500)
    )
    writer = csv.writer(_CsvBuffer())
    yield writer.writerow(
        (
            "created_at",
            "booking_reference",
            "movie",
            "theatre",
            "city",
            "show_start",
            "booking_status",
            "payment_status",
            "ticket_count",
            "total_amount",
        )
    )
    for booking in rows:
        yield writer.writerow(
            [
                _csv_safe(booking["created_at"].isoformat()),
                _csv_safe(booking["booking_reference"]),
                _csv_safe(booking["show__movie__title"]),
                _csv_safe(booking["show__screen__theatre__name"]),
                _csv_safe(booking["show__screen__theatre__city"]),
                _csv_safe(booking["show__start_time"].isoformat()),
                _csv_safe(booking["status"]),
                _csv_safe(booking["payment_status"]),
                _csv_safe(booking["ticket_count"]),
                _csv_safe(booking["total_amount"]),
            ]
        )


@_staff_required
def export_bookings_csv(request):
    start, end, errors = _date_range(request)
    if errors:
        return HttpResponseBadRequest(" ".join(errors))
    response = StreamingHttpResponse(
        _csv_rows(start, end), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="analytics-{start.isoformat()}-{end.isoformat()}.csv"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response

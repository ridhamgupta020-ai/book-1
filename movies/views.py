from datetime import datetime
from django.core.paginator import Paginator
from django.db import OperationalError, ProgrammingError
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from bookmyseat.bootstrap import ensure_database_ready
from .forms import MovieFilterForm
from .models import Movie, Show, Theatre


def home_view(request):
    try:
        featured_movies = list(
            Movie.objects.filter(is_featured=True, status=Movie.Status.NOW_SHOWING)[:4]
        )
        now_showing = list(Movie.objects.filter(status=Movie.Status.NOW_SHOWING)[:8])
        coming_soon = list(Movie.objects.filter(status=Movie.Status.COMING_SOON)[:4])
        theatres = list(Theatre.objects.filter(is_active=True)[:6])
    except (OperationalError, ProgrammingError):
        ensure_database_ready()
        featured_movies = list(
            Movie.objects.filter(is_featured=True, status=Movie.Status.NOW_SHOWING)[:4]
        )
        now_showing = list(Movie.objects.filter(status=Movie.Status.NOW_SHOWING)[:8])
        coming_soon = list(Movie.objects.filter(status=Movie.Status.COMING_SOON)[:4])
        theatres = list(Theatre.objects.filter(is_active=True)[:6])

    return render(
        request,
        "home.html",
        {
            "featured_movies": featured_movies,
            "now_showing": now_showing,
            "coming_soon": coming_soon,
            "theatres": theatres,
        },
    )


def movie_list_view(request):
    form = MovieFilterForm(request.GET or None)
    queryset = Movie.objects.exclude(status=Movie.Status.ARCHIVED)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        genre = form.cleaned_data.get("genre")
        language = form.cleaned_data.get("language")
        status = form.cleaned_data.get("status")
        sort = form.cleaned_data.get("sort") or "-release_date"

        if q:
            queryset = queryset.filter(
                Q(title__icontains=q)
                | Q(director__icontains=q)
                | Q(cast__icontains=q)
            )
        if genre:
            queryset = queryset.filter(genre__iexact=genre)
        if language:
            queryset = queryset.filter(language__iexact=language)
        if status:
            queryset = queryset.filter(status=status)
        if sort in {"-release_date", "title", "duration_minutes"}:
            queryset = queryset.order_by(sort)

    paginator = Paginator(queryset, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    genres = (
        Movie.objects.exclude(status=Movie.Status.ARCHIVED)
        .values_list("genre", flat=True)
        .distinct()
    )
    languages = (
        Movie.objects.exclude(status=Movie.Status.ARCHIVED)
        .values_list("language", flat=True)
        .distinct()
    )

    return render(
        request,
        "movies/movie_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "genres": sorted(set(genres)),
            "languages": sorted(set(languages)),
        },
    )


def movie_detail_view(request, slug):
    movie = get_object_or_404(Movie, slug=slug)
    selected_date_str = request.GET.get("date")
    selected_city = request.GET.get("city", "").strip()

    shows_qs = (
        Show.objects.filter(
            movie=movie,
            is_active=True,
            start_time__gte=timezone.now(),
        )
        .select_related("screen", "screen__theatre")
        .order_by("start_time")
    )

    if selected_city:
        shows_qs = shows_qs.filter(screen__theatre__city__iexact=selected_city)

    if selected_date_str:
        try:
            parsed_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
            shows_qs = shows_qs.filter(start_time__date=parsed_date)
        except ValueError:
            pass

    theatre_schedule = {}
    for show in shows_qs:
        theatre = show.screen.theatre
        theatre_schedule.setdefault(theatre, []).append(show)

    cities = (
        Theatre.objects.filter(is_active=True)
        .values_list("city", flat=True)
        .distinct()
    )

    return render(
        request,
        "movies/movie_detail.html",
        {
            "movie": movie,
            "theatre_schedule": theatre_schedule,
            "cities": sorted(set(cities)),
            "selected_city": selected_city,
            "selected_date": selected_date_str or "",
        },
    )


def theatre_list_view(request):
    city = request.GET.get("city", "").strip()
    theatres = Theatre.objects.filter(is_active=True).prefetch_related("screens")
    if city:
        theatres = theatres.filter(city__iexact=city)
    cities = (
        Theatre.objects.filter(is_active=True)
        .values_list("city", flat=True)
        .distinct()
    )
    return render(
        request,
        "movies/theatre_list.html",
        {
            "theatres": theatres,
            "cities": sorted(set(cities)),
            "selected_city": city,
        },
    )

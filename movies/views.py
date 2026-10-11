from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, ProgrammingError
from django.db.models import Case, Count, F, IntegerField, Min, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from bookmyseat.bootstrap import ensure_database_ready
from bookings.models import Booking
from .forms import MovieFilterForm, ReviewForm, ReviewReportForm
from .models import Movie, Review, ReviewReport, Show, Theatre


def home_view(request):
    recent_cutoff = timezone.now() - timedelta(days=30)
    try:
        featured_movies = list(
            Movie.objects.filter(is_featured=True, status=Movie.Status.NOW_SHOWING)[:4]
        )
        now_showing = list(Movie.objects.filter(status=Movie.Status.NOW_SHOWING)[:8])
        coming_soon = list(Movie.objects.filter(status=Movie.Status.COMING_SOON)[:4])
        theatres = list(Theatre.objects.filter(is_active=True)[:6])
        trending_movies = list(
            Movie.objects.exclude(status=Movie.Status.ARCHIVED)
            .annotate(
                recent_bookings=Count(
                    "shows__bookings",
                    filter=Q(
                        shows__bookings__status=Booking.Status.CONFIRMED,
                        shows__bookings__created_at__gte=recent_cutoff,
                    ),
                    distinct=True,
                )
            )
            .order_by("-recent_bookings", "-rating", "-release_date")[:4]
        )
    except (OperationalError, ProgrammingError):
        ensure_database_ready()
        featured_movies = list(
            Movie.objects.filter(is_featured=True, status=Movie.Status.NOW_SHOWING)[:4]
        )
        now_showing = list(Movie.objects.filter(status=Movie.Status.NOW_SHOWING)[:8])
        coming_soon = list(Movie.objects.filter(status=Movie.Status.COMING_SOON)[:4])
        theatres = list(Theatre.objects.filter(is_active=True)[:6])
        trending_movies = list(
            Movie.objects.exclude(status=Movie.Status.ARCHIVED)
            .annotate(
                recent_bookings=Count(
                    "shows__bookings",
                    filter=Q(
                        shows__bookings__status=Booking.Status.CONFIRMED,
                        shows__bookings__created_at__gte=recent_cutoff,
                    ),
                    distinct=True,
                )
            )
            .order_by("-recent_bookings", "-rating", "-release_date")[:4]
        )

    return render(
        request,
        "home.html",
        {
            "featured_movies": featured_movies,
            "now_showing": now_showing,
            "coming_soon": coming_soon,
            "theatres": theatres,
            "trending_movies": trending_movies,
            "top_rated_movies": Movie.objects.exclude(
                status=Movie.Status.ARCHIVED
            ).order_by("-rating", "-release_date")[:4],
        },
    )


def movie_list_view(request):
    form = MovieFilterForm(request.GET or None)
    queryset = Movie.objects.exclude(status=Movie.Status.ARCHIVED)
    now = timezone.now()

    if form.is_valid():
        q = form.cleaned_data.get("q")
        genre = form.cleaned_data.get("genre")
        language = form.cleaned_data.get("language")
        city = form.cleaned_data.get("city")
        theatre = form.cleaned_data.get("theatre")
        release_from = form.cleaned_data.get("release_from")
        release_to = form.cleaned_data.get("release_to")
        min_rating = form.cleaned_data.get("min_rating")
        showtime = form.cleaned_data.get("showtime")
        status = form.cleaned_data.get("status")
        sort = form.cleaned_data.get("sort") or "-release_date"

        if q:
            queryset = queryset.filter(title__icontains=q)
        if genre:
            queryset = queryset.filter(genre__iexact=genre)
        if language:
            queryset = queryset.filter(language__iexact=language)
        if release_from:
            queryset = queryset.filter(release_date__gte=release_from)
        if release_to:
            queryset = queryset.filter(release_date__lte=release_to)
        if min_rating is not None:
            queryset = queryset.filter(rating__gte=min_rating)
        if status:
            queryset = queryset.filter(status=status)
        show_filters = Q(
            shows__is_active=True,
            shows__start_time__gte=now,
            shows__screen__theatre__is_active=True,
        )
        if city:
            show_filters &= Q(shows__screen__theatre__city__iexact=city)
        if theatre:
            show_filters &= Q(shows__screen__theatre_id=theatre)
        if showtime == "morning":
            show_filters &= Q(shows__start_time__hour__lt=12)
        elif showtime == "afternoon":
            show_filters &= Q(
                shows__start_time__hour__gte=12, shows__start_time__hour__lt=17
            )
        elif showtime == "evening":
            show_filters &= Q(shows__start_time__hour__gte=17)
        if city or theatre or showtime:
            queryset = queryset.filter(show_filters)

        queryset = queryset.annotate(
            popularity=Count(
                "shows__bookings",
                filter=Q(shows__bookings__status=Booking.Status.CONFIRMED),
                distinct=True,
            ),
            lowest_ticket_price=Min("shows__ticket_price", filter=show_filters),
        ).distinct()
        sort_map = {
            "popularity": ("-popularity", "-release_date", "title"),
            "-release_date": ("-release_date", "title"),
            "-rating": ("-rating", "-release_date", "title"),
            "ticket_price": (
                F("lowest_ticket_price").asc(nulls_last=True),
                "-release_date",
                "title",
            ),
            "-ticket_price": (
                F("lowest_ticket_price").desc(nulls_last=True),
                "-release_date",
                "title",
            ),
        }
        queryset = queryset.order_by(*sort_map.get(sort, sort_map["-release_date"]))

    if request.GET.get("count_only") == "1":
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        return JsonResponse({"count": queryset.count()})

    paginator = Paginator(queryset, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    matching_count = queryset.count()

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
    cities = Theatre.objects.filter(is_active=True).values_list("city", flat=True).distinct()
    theatres = Theatre.objects.filter(is_active=True).order_by("city", "name")

    recent_movie_ids = request.session.get("recently_viewed_movies", [])
    booked_movie_ids = []
    preferred_genres = []
    preferred_languages = []
    if request.user.is_authenticated:
        booking_history = Booking.objects.filter(
            user=request.user, status=Booking.Status.CONFIRMED
        ).select_related("show__movie")
        booked_movie_ids = list(
            booking_history.values_list("show__movie_id", flat=True).distinct()
        )
        preferred_genres = list(
            booking_history.values_list("show__movie__genre", flat=True).distinct()
        )
        preferred_languages = list(
            booking_history.values_list("show__movie__language", flat=True).distinct()
        )

    viewed_movies = Movie.objects.filter(pk__in=recent_movie_ids)
    preferred_genres.extend(viewed_movies.values_list("genre", flat=True))
    preferred_languages.extend(viewed_movies.values_list("language", flat=True))
    recommendation_query = Q(genre__in=set(preferred_genres)) | Q(
        language__in=set(preferred_languages)
    )
    if preferred_genres or preferred_languages:
        recommendations = (
            Movie.objects.exclude(status=Movie.Status.ARCHIVED)
            .exclude(pk__in=booked_movie_ids)
            .exclude(pk__in=recent_movie_ids)
            .filter(recommendation_query)
            .annotate(
                popularity=Count(
                    "shows__bookings",
                    filter=Q(shows__bookings__status=Booking.Status.CONFIRMED),
                    distinct=True,
                )
            )
            .order_by("-popularity", "-rating", "-release_date")[:4]
        )
    else:
        recommendations = Movie.objects.none()

    return render(
        request,
        "movies/movie_list.html",
        {
            "form": form,
            "page_obj": page_obj,
            "genres": sorted(set(genres)),
            "languages": sorted(set(languages)),
            "cities": sorted(set(cities)),
            "theatres": theatres,
            "matching_count": matching_count,
            "recommendations": recommendations,
        },
    )


def movie_detail_view(request, slug):
    movie = get_object_or_404(Movie.objects.prefetch_related("posters"), slug=slug)
    recent_movie_ids = request.session.get("recently_viewed_movies", [])
    recent_movie_ids = [movie_id for movie_id in recent_movie_ids if movie_id != movie.id]
    request.session["recently_viewed_movies"] = [movie.id, *recent_movie_ids[:9]]
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
    review_queryset = movie.reviews.filter(
        moderation_status=Review.ModerationStatus.PUBLISHED
    ).select_related("user", "booking")
    review_form = None
    eligible_bookings = Booking.objects.none()
    if request.user.is_authenticated:
        eligible_bookings = Booking.objects.filter(
            user=request.user,
            show__movie=movie,
            status=Booking.Status.CONFIRMED,
            payment_status=Booking.PaymentStatus.PAID,
            checked_in_at__isnull=False,
            show__end_time__lt=timezone.now(),
        ).exclude(movie_reviews__isnull=False)
        if eligible_bookings.exists():
            review_form = ReviewForm(request.user, movie)

    movie_year = movie.release_date.year
    similar_movies = (
        Movie.objects.exclude(pk=movie.pk)
        .exclude(status=Movie.Status.ARCHIVED)
        .filter(Q(genre=movie.genre) | Q(language=movie.language))
        .annotate(
            similarity_score=(
                Case(
                    When(genre=movie.genre, then=Value(3)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                + Case(
                    When(language=movie.language, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                + Case(
                    When(
                        Q(
                            release_date__year__gte=movie_year - 3,
                            release_date__year__lte=movie_year + 3,
                        ),
                        then=Value(1),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            popularity=Count(
                "shows__bookings",
                filter=Q(shows__bookings__status=Booking.Status.CONFIRMED),
                distinct=True,
            ),
        )
        .order_by("-similarity_score", "-popularity", "-rating")[:4]
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
            "reviews": review_queryset,
            "review_count": review_queryset.count(),
            "poster_gallery": list(movie.posters.all()),
            "review_form": review_form,
            "eligible_bookings": eligible_bookings,
            "similar_movies": similar_movies,
        },
    )


@login_required
@require_POST
def create_review_view(request, slug):
    movie = get_object_or_404(Movie, slug=slug)
    form = ReviewForm(request.user, movie, request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        try:
            review.save()
        except IntegrityError:
            messages.error(request, "You have already reviewed this viewing.")
        else:
            messages.success(
                request,
                "Your review was submitted and will appear after moderation.",
            )
    else:
        messages.error(request, "A completed, staff-verified viewing is required to review.")
    return redirect(movie.get_absolute_url())


@login_required
@require_POST
def edit_review_view(request, review_id):
    review = get_object_or_404(Review, pk=review_id, user=request.user)
    form = ReviewForm(
        request.user, review.movie, request.POST, instance=review
    )
    if form.is_valid():
        try:
            updated_review = form.save(commit=False)
            updated_review.moderation_status = Review.ModerationStatus.PENDING
            updated_review.save()
        except IntegrityError:
            messages.error(request, "This viewing already has a review.")
        else:
            messages.success(request, "Your updated review is awaiting moderation.")
    else:
        messages.error(request, "Please correct the review before saving.")
    return redirect(review.movie.get_absolute_url())


@login_required
@require_POST
def report_review_view(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    if review.user_id == request.user.id:
        messages.error(request, "You cannot report your own review.")
        return redirect(review.movie.get_absolute_url())
    form = ReviewReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.review = review
        report.reporter = request.user
        try:
            report.save()
        except IntegrityError:
            messages.info(request, "You have already reported this review.")
        else:
            messages.success(request, "The review was reported for moderation.")
    else:
        messages.error(request, "Please select a valid report reason.")
    return redirect(review.movie.get_absolute_url())


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

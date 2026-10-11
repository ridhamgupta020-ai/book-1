from django.urls import path
from . import views

app_name = "movies"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("movies/", views.movie_list_view, name="movie_list"),
    path("movies/<slug:slug>/", views.movie_detail_view, name="movie_detail"),
    path(
        "movies/<slug:slug>/reviews/",
        views.create_review_view,
        name="create_review",
    ),
    path(
        "reviews/<int:review_id>/edit/",
        views.edit_review_view,
        name="edit_review",
    ),
    path(
        "reviews/<int:review_id>/report/",
        views.report_review_view,
        name="report_review",
    ),
    path("theatres/", views.theatre_list_view, name="theatre_list"),
]
